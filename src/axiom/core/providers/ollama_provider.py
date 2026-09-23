"""Ollama как Provider: мост к существующему OllamaClient."""
from __future__ import annotations

from axiom.core.ollama import OllamaClient
from axiom.core.providers.base import (
    ChatMessage,
    ChatResult,
    ModelProfile,
    Provider,
    ProviderCapabilities,
    ProviderStatus,
    StreamChunk,
    ToolCall,
)


class OllamaProvider(Provider):
    id = "ollama"
    label = "Ollama"

    def __init__(self, base_url="http://127.0.0.1:11434", *, keep_alive=None):
        self.base_url = base_url
        self._client = OllamaClient(base_url, keep_alive=keep_alive)
        self._models_cache: list[dict] = []

    async def authenticate(self) -> ProviderStatus:
        try:
            ok = await self._client.is_available()
            return ProviderStatus.CONNECTED if ok else ProviderStatus.NOT_CONFIGURED
        except Exception:
            return ProviderStatus.ERROR

    async def list_models(self) -> list[ModelProfile]:
        try:
            raw = await self._client.list_models()
        except Exception:
            return []
        out: list[ModelProfile] = []
        for item in raw:
            name = str(item.get("name") or item.get("model") or "")
            if not name:
                continue
            raw_caps = item.get("capabilities")
            caps = [str(c) for c in raw_caps] if isinstance(raw_caps, list) else []
            low = name.lower()
            out.append(ModelProfile(
                id=name, provider_id="ollama", display_name=name,
                coding=any(k in low for k in ("code", "coder", "qwen", "deepseek", "glm")),
                reasoning="thinking" in caps or "r1" in low or "think" in low,
                tool_calling="tools" in caps, long_context=False,
                vision="vision" in caps))
        out.sort(key=lambda m: m.id.lower())
        return out

    def _msgs(self, messages: list[ChatMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

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
        async for ch in self._client.chat(model, self._msgs(messages), think=think,
                                          tools=tools, options=options, keep_alive=None):
            yield StreamChunk(thinking=ch.thinking, content=ch.content, done=ch.done,
                tool_calls=[ToolCall(name=t.name, arguments=t.arguments) for t in ch.tool_calls],
                metrics=dict(ch.metrics or {}))

    def supports_tools(self, model=None):
        return None

    def supports_reasoning(self, model=None):
        return None

    def supports_vision(self, model=None):
        return None

    def supports_prompt_cache(self, model=None):
        return False

    def capabilities(self, model=None) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True, reasoning=True, streaming=True)
