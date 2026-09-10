"""OpenAI-compatible chat-completions provider (works for many vendors)."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from axiom.core.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from axiom.core.logging import get_logger
from axiom.models.provider import ChatResponse, ModelProvider, StreamChunk, ToolSpec, Usage
from axiom.models.streaming import ToolCallAccumulator

logger = get_logger("openai_compatible")


def raise_for_status(status: int, body: str) -> None:
    """Map an HTTP status to a typed provider error."""
    if status < 400:
        return
    if status in (401, 403):
        raise ProviderAuthError(f"Provider auth failed (HTTP {status}): {body[:200]}")
    if status == 429:
        raise ProviderRateLimitError(f"Rate limited (HTTP 429): {body[:200]}")
    if status == 408:
        raise ProviderTimeoutError("Request timeout (HTTP 408)")
    if status == 404:
        raise ProviderError(f"Endpoint/model not found (HTTP 404): {body[:200]}")
    raise ProviderError(f"Provider error (HTTP {status}): {body[:200]}")


class OpenAICompatibleProvider(ModelProvider):
    """Universal provider for OpenAI-compatible /chat/completions APIs."""

    name = "openai_compatible"

    def __init__(
        self,
        model: str = "GPT-OSS-120B",
        base_url: str = "https://api.groq.com/openai/v1",
        api_key: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self.model_name = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._headers = headers or {}
        self._timeout = timeout
        self._max_retries = max_retries
        self.supports_streaming = True
        self.supports_tools = True

    # -- request building ------------------------------------------------
    def _request_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self._headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _build_messages(
        self, messages: list[dict[str, Any]], system: str | None = None
    ) -> list[dict[str, Any]]:
        result = []
        if system:
            result.append({"role": "system", "content": system})
        for message in messages:
            converted: dict[str, Any] = {
                "role": message["role"], "content": message.get("content", "")
            }
            if message.get("tool_call_id"):
                converted["tool_call_id"] = message["tool_call_id"]
            if message.get("name"):
                converted["name"] = message["name"]
            if message.get("tool_calls"):
                converted["tool_calls"] = self._serialize_calls(message["tool_calls"])
            result.append(converted)
        return result

    @staticmethod
    def _serialize_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        serialized = []
        for call in calls:
            args = call.get("arguments", {})
            serialized.append({
                "id": call.get("id", "call_0"),
                "type": "function",
                "function": {
                    "name": call.get("name", ""),
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            })
        return serialized

    # -- HTTP ------------------------------------------------------------
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> ChatResponse:
        """Send a non-streaming chat completion."""
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": self._build_messages(messages, system),
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        tool_payload = self._build_tools(tools)
        if tool_payload:
            payload["tools"] = tool_payload
        body = await self._post("/chat/completions", payload)
        return self._parse_response(body)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        last_error: Exception | None = None
        for _attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        url, json=payload, headers=self._request_headers()
                    )
                raise_for_status(response.status_code, response.text)
                return response.json()
            except (ProviderAuthError, ProviderRateLimitError):
                raise
            except (httpx.TimeoutException, ProviderTimeoutError) as exc:
                last_error = ProviderTimeoutError(f"Provider timeout: {exc}")
            except (httpx.HTTPError, ProviderError, json.JSONDecodeError) as exc:
                last_error = exc
        raise ProviderUnavailableError(f"Provider unreachable: {last_error}")

    def _parse_response(self, body: dict[str, Any]) -> ChatResponse:
        try:
            choice = body["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Malformed provider response: {exc}") from exc
        usage_data = body.get("usage") or {}
        usage = Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )
        tool_calls = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments", "")}
            tool_calls.append(
                {"id": raw.get("id", "call_0"), "name": fn.get("name", ""), "arguments": args}
            )
        return ChatResponse(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            usage=usage,
            model=body.get("model", self.model_name),
            finish_reason=choice.get("finish_reason", ""),
        )

    async def validate(self) -> bool:
        try:
            body = await self._post(
                "/chat/completions",
                {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
            return "choices" in body
        except ProviderError:
            return False

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat completion chunks (SSE)."""
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": self._build_messages(messages, system),
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        tool_payload = self._build_tools(tools)
        if tool_payload:
            payload["tools"] = tool_payload
        url = f"{self._base_url}/chat/completions"
        accumulator = ToolCallAccumulator()
        start = time.monotonic()
        output_tokens = 0
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST", url, json=payload, headers=self._request_headers()
                ) as response:
                    if response.status_code >= 400:
                        raw = (await response.aread()).decode("utf-8", "replace")
                        raise_for_status(response.status_code, raw)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        for tc in delta.get("tool_calls") or []:
                            accumulator.add(tc)
                        text = delta.get("content") or ""
                        if text:
                            output_tokens += 1
                            yield StreamChunk(delta=text)
                        finish = choices[0].get("finish_reason")
                        if finish:
                            elapsed = max(0.001, time.monotonic() - start)
                            usage_data = chunk.get("usage") or {}
                            yield StreamChunk(
                                finish_reason=finish,
                                tool_calls=accumulator.finalize(),
                                usage=Usage(
                                    input_tokens=usage_data.get("prompt_tokens", 0),
                                    output_tokens=usage_data.get("completion_tokens", output_tokens),
                                    tokens_per_second=output_tokens / elapsed,
                                ),
                            )
        except (httpx.TimeoutException, ProviderTimeoutError) as exc:
            raise ProviderTimeoutError(f"Provider stream timeout: {exc}") from exc
        except (httpx.HTTPError, ProviderError) as exc:
            raise ProviderError(f"Provider stream failed: {exc}") from exc
        calls = accumulator.finalize()
        if calls:
            yield StreamChunk(
                tool_calls=calls,
                finish_reason="tool_calls",
                usage=Usage(output_tokens=output_tokens),
            )


    def _build_tools(self, tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
