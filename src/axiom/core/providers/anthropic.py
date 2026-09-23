"""Anthropic Messages API адаптер."""
from __future__ import annotations

import json as _json

import httpx

from axiom.core.providers.base import (
    ChatResult,
    ModelProfile,
    Provider,
    ProviderAuthError,
    ProviderCapabilities,
    ProviderError,
    ProviderStatus,
    ProviderUnavailableError,
    StreamChunk,
    ToolCall,
)


class AnthropicProvider(Provider):
    def __init__(self, api_key="", *, base_url="https://api.anthropic.com", timeout=600.0):
        self.id = "anthropic"
        self.label = "Anthropic"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _h(self) -> dict:
        h = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    async def authenticate(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus.NOT_CONFIGURED
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{self.base_url}/v1/models", headers=self._h())
            if r.status_code == 401:
                return ProviderStatus.ERROR
            return ProviderStatus.CONNECTED if r.status_code < 500 else ProviderStatus.ERROR
        except Exception:
            return ProviderStatus.ERROR

    async def list_models(self) -> list[ModelProfile]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=20.0) as c:
                r = await c.get(f"{self.base_url}/v1/models", headers=self._h())
            if r.status_code == 401:
                raise ProviderAuthError("Anthropic: invalid API key")
            if r.status_code >= 400:
                raise ProviderError(f"Anthropic: HTTP {r.status_code}")
            data = r.json()
            items = data.get("data", []) if isinstance(data, dict) else []
            out = [ModelProfile(id=str(e.get("id", "")), provider_id="anthropic",
                display_name=str(e.get("id", "")), coding=True, reasoning=True,
                tool_calling=True, long_context=True)
                for e in items if isinstance(e, dict) and e.get("id")]
            out.sort(key=lambda m: m.id.lower())
            return out
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"Anthropic: {exc}") from exc

    async def chat(self, model, messages, *, tools=None, think=None, options=None) -> ChatResult:
        chunks: list[StreamChunk] = []
        async for ch in self.stream(model, messages, tools=tools, think=think, options=options):
            chunks.append(ch)
        calls: list[ToolCall] = []
        for ch in chunks:
            calls.extend(ch.tool_calls)
        return ChatResult(content="".join(c.content for c in chunks),
                          thinking="".join(c.thinking for c in chunks), tool_calls=calls)

    async def stream(self, model, messages, *, tools=None, think=None, options=None):
        system = ""
        msgs: list[dict] = []
        for m in messages:
            if m.role == "system":
                system += m.content + "\n"
            else:
                msgs.append({"role": m.role if m.role in ("user", "assistant") else "user",
                             "content": m.content})
        payload: dict = {"model": model, "messages": msgs or [{"role": "user", "content": ""}],
                         "max_tokens": (options or {}).get("max_tokens", 1024), "stream": True}
        if system.strip():
            payload["system"] = system.strip()
        if tools:
            payload["tools"] = [
                {
                    "name": tool.get("function", {}).get("name", tool.get("name", "")),
                    "description": tool.get("function", {}).get("description", tool.get("description", "")),
                    "input_schema": tool.get("function", {}).get(
                        "parameters", tool.get("input_schema", {"type": "object"})
                    ),
                }
                for tool in tools
                if tool.get("function", {}).get("name") or tool.get("name")
            ]
        calls: dict[str, dict] = {}
        try:
            async with (
                httpx.AsyncClient(timeout=self.timeout) as client,
                client.stream("POST", f"{self.base_url}/v1/messages",
                              headers=self._h(), json=payload) as resp,
            ):
                    if resp.status_code == 401:
                        raise ProviderAuthError("Anthropic: invalid API key")
                    if resp.status_code == 429:
                        raise ProviderUnavailableError("Anthropic: rate limited (429)")
                    if resp.status_code >= 400:
                        body = (await resp.aread())[:300].decode("utf-8", errors="replace")
                        raise ProviderError(f"Anthropic: HTTP {resp.status_code}: {body}")
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            obj = _json.loads(line[5:].strip())
                        except Exception:
                            continue
                        delta = obj.get("delta", {}) if isinstance(obj.get("delta"), dict) else {}
                        if obj.get("type") == "content_block_delta" and "text" in delta:
                            yield StreamChunk(content=str(delta.get("text", "")))
                        elif obj.get("type") == "content_block_delta" and "thinking" in delta:
                            yield StreamChunk(thinking=str(delta.get("thinking", "")))
                        elif (obj.get("type") == "content_block_start"
                              and obj.get("content_block", {}).get("type") == "tool_use"):
                            block = obj["content_block"]
                            calls[str(block.get("id") or block.get("name") or "tool")] = {
                                "name": str(block.get("name") or ""), "arguments": {},
                            }
                        elif obj.get("type") == "content_block_delta" and "input_json_delta" in delta:
                            block_id = str(obj.get("index", "0"))
                            call = calls.get(block_id) or calls.setdefault(block_id, {"name": "", "arguments": {}})
                            call["arguments"].setdefault("_raw", "")
                            call["arguments"]["_raw"] += str(delta["input_json_delta"].get("partial_json", ""))
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"Anthropic: {exc}") from exc
        final_calls = []
        for call in calls.values():
            arguments = dict(call["arguments"])
            raw = arguments.pop("_raw", "")
            if isinstance(raw, str) and raw:
                try:
                    parsed = _json.loads(raw)
                    if isinstance(parsed, dict):
                        arguments = parsed
                except _json.JSONDecodeError:
                    pass
            if call["name"]:
                final_calls.append(ToolCall(name=call["name"], arguments=arguments))
        yield StreamChunk(done=True, tool_calls=final_calls)

    def supports_tools(self, model=None):
        return True

    def supports_reasoning(self, model=None):
        return True

    def supports_vision(self, model=None):
        return None

    def supports_prompt_cache(self, model=None):
        return True

    def capabilities(self, model=None) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True, reasoning=True, streaming=True, long_context=True)
