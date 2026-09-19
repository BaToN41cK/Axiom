"""Ollama HTTP client and adaptive streaming response parser.

Verified against the real Ollama API (observed live behaviour):

* ``GET  /api/version`` — health probe, returns ``{"version": "..."}``.
* ``GET  /api/tags``    — model discovery; each model carries a
  ``capabilities`` list (e.g. ``completion, tools, thinking, vision``).
* ``POST /api/chat``    — streaming NDJSON. Each chunk is a delta; the final
  chunk has ``done: true`` with ``done_reason`` and metrics, its message
  content/thinking fields are empty.

The ``think`` request parameter enables reasoning separation, but models may
emit ``thinking`` even when it is not requested — the parser treats the
``thinking`` field as authoritative whenever present. Legacy models embed
``<think>...</think>`` inside ``content``; the parser separates those too.

This module is frontend-agnostic and imports no UI code.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from axiom.core.errors import (
    InvalidResponseError,
    ModelNotFoundError,
    OllamaUnavailableError,
)

_DEFAULT_TIMEOUT = httpx.Timeout(600.0, connect=10.0)
_PROBE_TIMEOUT = httpx.Timeout(4.0, connect=3.0)

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


@dataclass
class ToolCallRequest:
    """A tool call requested by the model."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """A normalised chunk of a chat stream."""

    thinking: str = ""
    content: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    done: bool = False
    done_reason: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


class ChatStreamParser:
    """Adaptive parser for Ollama ``/api/chat`` NDJSON streams.

    Handles: reasoning deltas, content deltas, tool calls, the final metadata
    chunk, legacy ``<think>`` tags inside content, malformed lines and
    unexpected fields (which are ignored, never crash the stream).
    """

    def __init__(self) -> None:
        self._in_legacy_think = False
        self._legacy_buffer = ""  # partial tag at chunk boundary

    def feed_line(self, line: str) -> StreamChunk:
        """Parse one NDJSON line into a normalised :class:`StreamChunk`."""
        if not line or not line.strip():
            return StreamChunk()
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InvalidResponseError(f"Malformed stream line: {exc}") from exc
        if not isinstance(obj, dict):
            raise InvalidResponseError("Stream line is not a JSON object")

        if obj.get("error"):
            raise InvalidResponseError(str(obj["error"]))

        chunk = StreamChunk(
            done=bool(obj.get("done", False)),
            done_reason=obj.get("done_reason"),
        )
        if chunk.done:
            chunk.metrics = {
                k: obj[k]
                for k in (
                    "total_duration",
                    "load_duration",
                    "prompt_eval_count",
                    "prompt_eval_duration",
                    "eval_count",
                    "eval_duration",
                )
                if k in obj
            }

        message = obj.get("message") or {}
        if isinstance(message, dict):
            # Reasoning field — authoritative when present, regardless of the
            # ``think`` request parameter (models may ignore it).
            thinking = message.get("thinking")
            if isinstance(thinking, str) and thinking:
                chunk.thinking += thinking

            content = message.get("content")
            if isinstance(content, str) and content:
                text, legacy_think = self._split_legacy_think(content)
                chunk.content += text
                chunk.thinking += legacy_think

            calls = message.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    fn = call.get("function") or {}
                    name = fn.get("name")
                    if not name:
                        continue
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args) if args.strip() else {}
                        except json.JSONDecodeError:
                            args = {"_raw": args}
                    if not isinstance(args, dict):
                        args = {"_raw": args}
                    chunk.tool_calls.append(ToolCallRequest(name=name, arguments=args))

        return chunk

    def _split_legacy_think(self, text: str) -> tuple[str, str]:
        """Separate legacy ``<think>`` regions embedded in content.

        Handles partial tags spanning chunk boundaries via a small buffer.
        """
        self._legacy_buffer += text
        out: list[str] = []
        think: list[str] = []
        while self._legacy_buffer:
            if self._in_legacy_think:
                idx = self._legacy_buffer.find(_THINK_CLOSE)
                if idx == -1:
                    keep = self._partial_suffix(self._legacy_buffer, _THINK_CLOSE)
                    emit_len = len(self._legacy_buffer) - keep
                    think.append(self._legacy_buffer[:emit_len])
                    self._legacy_buffer = self._legacy_buffer[emit_len:]
                    break
                think.append(self._legacy_buffer[:idx])
                self._legacy_buffer = self._legacy_buffer[idx + len(_THINK_CLOSE):]
                self._in_legacy_think = False
            else:
                idx = self._legacy_buffer.find(_THINK_OPEN)
                if idx == -1:
                    keep = self._partial_suffix(self._legacy_buffer, _THINK_OPEN)
                    emit_len = len(self._legacy_buffer) - keep
                    out.append(self._legacy_buffer[:emit_len])
                    self._legacy_buffer = self._legacy_buffer[emit_len:]
                    break
                out.append(self._legacy_buffer[:idx])
                self._legacy_buffer = self._legacy_buffer[idx + len(_THINK_OPEN):]
                self._in_legacy_think = True
        return "".join(out), "".join(think)

    @staticmethod
    def _partial_suffix(buffer: str, tag: str) -> int:
        """Length of the longest suffix of *buffer* that is a prefix of *tag*."""
        max_len = min(len(buffer), len(tag) - 1)
        for size in range(max_len, 0, -1):
            if buffer.endswith(tag[:size]):
                return size
        return 0

    def flush(self) -> StreamChunk:
        """Flush any buffered legacy-tag tail at end of stream."""
        buffered, self._legacy_buffer = self._legacy_buffer, ""
        if not buffered:
            return StreamChunk()
        if self._in_legacy_think:
            return StreamChunk(thinking=buffered)
        return StreamChunk(content=buffered)


class OllamaClient:
    """Async HTTP client for a local (or remote) Ollama server."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        self._base_url = base_url.rstrip("/")

    @property
    def base_url(self) -> str:
        return self._base_url

    def _client(self, timeout: httpx.Timeout = _DEFAULT_TIMEOUT) -> httpx.AsyncClient:
        # trust_env=False: a system proxy must never intercept localhost traffic.
        return httpx.AsyncClient(base_url=self._base_url, timeout=timeout, trust_env=False)

    async def is_available(self) -> bool:
        """Cheap health probe."""
        try:
            async with self._client(_PROBE_TIMEOUT) as client:
                response = await client.get("/api/version")
                return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    async def version(self) -> str:
        try:
            async with self._client(_PROBE_TIMEOUT) as client:
                response = await client.get("/api/version")
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                "Unable to reach the Ollama server.",
                hint=f"Check that Ollama is running at {self._base_url}",
            ) from exc
        version = data.get("version") if isinstance(data, dict) else None
        return str(version) if version else "unknown"

    async def list_models(self) -> list[dict[str, Any]]:
        """Raw model descriptors from ``/api/tags``."""
        try:
            async with self._client(_PROBE_TIMEOUT) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                "Unable to reach the Ollama server.",
                hint=f"Check that Ollama is running at {self._base_url}",
            ) from exc
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list):
            raise InvalidResponseError("Unexpected /api/tags response shape.")
        return [m for m in models if isinstance(m, dict)]

    async def list_running(self) -> list[dict[str, Any]]:
        """Raw descriptors of models currently loaded in memory (``/api/ps``).

        Best-effort by design: a status indicator (``Ready`` vs ``Idle``) must
        never break the model list, so transport problems yield ``[]``.
        """
        try:
            async with self._client(_PROBE_TIMEOUT) as client:
                response = await client.get("/api/ps")
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, OSError, ValueError):
            return []
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list):
            return []
        return [m for m in models if isinstance(m, dict)]

    async def show_model(self, name: str) -> dict[str, Any]:
        """Real per-model detail from ``POST /api/show``.

        This is the only endpoint that exposes the true maximum context window
        (``model_info["<arch>.context_length"]``) and the effective ``num_ctx``
        send in ``parameters`` — used by the GUI context panel.
        """
        try:
            async with self._client(_PROBE_TIMEOUT) as client:
                response = await client.post("/api/show", json={"model": name})
                if response.status_code == 404:
                    raise ModelNotFoundError(f"Model '{name}' is not available in Ollama.")
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                "Unable to reach the Ollama server.",
                hint=f"Check that Ollama is running at {self._base_url}",
            ) from exc
        if not isinstance(data, dict):
            raise InvalidResponseError("Unexpected /api/show response shape.")
        return data

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        think: bool | None = None,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat generation as normalised :class:`StreamChunk` items."""
        return self._chat_stream(model, messages, think=think, tools=tools, options=options)

    async def _chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        think: bool | None = None,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if think is not None:
            payload["think"] = think
        if tools:
            payload["tools"] = tools
        if options:
            # Real Ollama generation parameters (temperature, num_ctx, ...).
            payload["options"] = options

        parser = ChatStreamParser()
        try:
            async with (
                self._client() as client,
                client.stream("POST", "/api/chat", json=payload) as response,
            ):

                    if response.status_code == 404:
                        body = await response.aread()
                        raise ModelNotFoundError(_extract_error(body) or f"Model '{model}' not found.")
                    if response.status_code != 200:
                        body = await response.aread()
                        raise InvalidResponseError(_extract_error(body) or f"HTTP {response.status_code}")
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        yield parser.feed_line(line)
        except httpx.TimeoutException as exc:
            raise OllamaUnavailableError("Ollama request timed out.") from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(
                "Connection to Ollama was lost.",
                hint=f"Check that Ollama is running at {self._base_url}",
            ) from exc
        finally:
            tail = parser.flush()
            if tail.thinking or tail.content:
                yield tail


def _extract_error(body: bytes) -> str | None:
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return None

