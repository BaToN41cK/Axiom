"""OpenAI-совместимый адаптер: один код для ~12 провайдеров."""
from __future__ import annotations

import json as _json

import httpx

from axiom.core.providers._helpers import headers, to_messages
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


class OpenAICompatibleProvider(Provider):
    def __init__(self, pid, label, base_url, api_key="", *, extra_headers=None, timeout=600.0):
        self.id = pid
        self.label = label
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = extra_headers or {}
        self.timeout = timeout

    async def authenticate(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus.NOT_CONFIGURED
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{self.base_url}/models", headers=headers(self.api_key, self.extra_headers))
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
                r = await c.get(f"{self.base_url}/models", headers=headers(self.api_key, self.extra_headers))
            if r.status_code == 401:
                raise ProviderAuthError(f"{self.label}: invalid API key")
            if r.status_code >= 400:
                raise ProviderError(f"{self.label}: HTTP {r.status_code}")
            data = r.json()
            items = data.get("data", []) if isinstance(data, dict) else []
            out: list[ModelProfile] = []
            for e in items:
                mid = str(e.get("id", "") if isinstance(e, dict) else "")
                if mid:
                    low = mid.lower()
                    out.append(ModelProfile(
                        id=mid, provider_id=self.id, display_name=mid,
                        coding=any(k in low for k in ("code", "coder", "glm", "deepseek")),
                        reasoning=any(k in low for k in ("reason", "r1", "opus", "pro")),
                        tool_calling=True,
                        long_context=any(k in low for k in ("128k", "200k", "opus", "pro", "max")),
                        vision=any(k in low for k in ("vision", "vl", "omni"))))
            out.sort(key=lambda m: m.id.lower())
            return out
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"{self.label}: {exc}") from exc

    def _payload(self, model, messages, tools, think, options, stream):
        p: dict = {"model": model, "messages": to_messages(messages), "stream": stream}
        if tools:
            p["tools"] = tools
        if options:
            if options.get("temperature") is not None:
                p["temperature"] = options["temperature"]
            if options.get("max_tokens") is not None:
                p["max_tokens"] = options["max_tokens"]
        if isinstance(think, str):
            p["reasoning_effort"] = think
        return p

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
        payload = self._payload(model, messages, tools, think, options, True)
        try:
            async with (
                httpx.AsyncClient(timeout=self.timeout) as client,
                client.stream("POST", f"{self.base_url}/chat/completions",
                              headers=headers(self.api_key, self.extra_headers),
                              json=payload) as resp,
            ):
                    if resp.status_code == 401:
                        raise ProviderAuthError(f"{self.label}: invalid API key")
                    if resp.status_code == 429:
                        raise ProviderUnavailableError(f"{self.label}: rate limited (429)")
                    if resp.status_code >= 400:
                        body = (await resp.aread())[:400].decode("utf-8", errors="replace")
                        raise ProviderError(f"{self.label}: HTTP {resp.status_code}: {body}")
                    calls: dict[int, ToolCall] = {}
                    async for line in resp.aiter_lines():
                        if not line.strip() or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            final_calls = []
                            for call in calls.values():
                                raw_args = call.arguments.pop("_raw", "")
                                if isinstance(raw_args, str) and raw_args:
                                    try:
                                        parsed = _json.loads(raw_args)
                                        if isinstance(parsed, dict):
                                            call.arguments = parsed
                                    except _json.JSONDecodeError:
                                        pass
                                final_calls.append(call)
                            yield StreamChunk(done=True, tool_calls=final_calls)
                            return
                        try:
                            obj = _json.loads(data)
                        except Exception:
                            continue
                        choices = obj.get("choices", []) if isinstance(obj, dict) else []
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {}) if isinstance(choices[0], dict) else {}
                        for raw in delta.get("tool_calls") or []:
                            index = int(raw.get("index", len(calls)))
                            fn = raw.get("function", {}) if isinstance(raw, dict) else {}
                            current = calls.setdefault(index, ToolCall(name=str(fn.get("name") or ""), arguments={}))
                            if fn.get("name"):
                                current.name = str(fn["name"])
                            args = fn.get("arguments")
                            if isinstance(args, str):
                                args += current.arguments.get("_raw", "")
                            if isinstance(args, str):
                                current.arguments["_raw"] = args
                            elif isinstance(args, dict):
                                current.arguments.update(args)
                        yield StreamChunk(
                            thinking=str(delta.get("reasoning_content") or delta.get("reasoning") or ""),
                            content=str(delta.get("content") or ""))
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"{self.label}: {exc}") from exc
        yield StreamChunk(done=True)

    def supports_tools(self, model=None):
        return True

    def supports_reasoning(self, model=None):
        return None

    def supports_vision(self, model=None):
        return None

    def supports_prompt_cache(self, model=None):
        return self.id in ("anthropic", "openai")

    def capabilities(self, model=None) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True, streaming=True)

