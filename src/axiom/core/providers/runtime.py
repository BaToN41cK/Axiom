"""Provider-backed chat client used by the common Agent loop."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from axiom.core.ollama import StreamChunk, ToolCallRequest
from axiom.core.providers.base import ChatMessage, Provider
from axiom.core.providers.manager import ProviderManager
from axiom.core.router import ModelRouter, RouteTarget


class ProviderChatClient:
    """Expose providers through the small OllamaClient surface used by Agent."""

    def __init__(self, manager: ProviderManager, router: ModelRouter,
                 *, default_provider: str = "ollama", default_model: str | None = None,
                 ollama_client=None) -> None:
        self.manager = manager
        self.router = router
        self.default_provider = default_provider
        self.default_model = default_model
        self.ollama_client = ollama_client
        self.last_route: dict[str, str] = {}
        self._retry_counts: dict[str, int] = {}

    def _target(self, user_text: str, model: str | None = None) -> RouteTarget:
        target = self.router.route(user_text, None)
        if target is not None and target.model:
            return target
        name = model if isinstance(model, str) else getattr(model, "name", None)
        return RouteTarget(self.default_provider, name or self.default_model or "", "default")

    async def chat(self, model: str, messages: list[dict[str, Any]], *, think=None,
                  tools: list[dict[str, Any]] | None = None, options=None,
                  keep_alive: str | None = None) -> AsyncIterator[StreamChunk]:
        user_text = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        target = self._target(str(user_text), model)
        while True:
            if target.provider_id == "ollama" and self.ollama_client is not None:
                name = target.model or self.default_model or ""
                self.last_route = {"provider_id": "ollama", "model": name}
                async for chunk in self.ollama_client.chat(
                    name, messages, think=think, tools=tools,
                    options=options, keep_alive=keep_alive,
                ):
                    yield chunk
                return
            provider: Provider = self.manager.get_provider(target.provider_id)
            saw_output = False
            try:
                self.last_route = {"provider_id": target.provider_id, "model": target.model}
                async for chunk in provider.stream(
                    target.model,
                    [
                        ChatMessage(
                            role=str(m.get("role") or "user"),
                            content=str(m.get("content") or ""),
                        )
                        for m in messages
                    ],
                    tools=tools, think=think, options=options,
                ):
                    if chunk.content or chunk.thinking or chunk.tool_calls:
                        saw_output = True
                    yield StreamChunk(
                        thinking=chunk.thinking, content=chunk.content, done=chunk.done,
                        tool_calls=[
                            ToolCallRequest(name=c.name, arguments=dict(c.arguments))
                            for c in chunk.tool_calls
                        ],
                        metrics=dict(chunk.metrics or {}),
                    )
                return
            except Exception as exc:
                if saw_output or not self.router.should_fallback(exc):
                    raise
                key = f"{target.provider_id}/{target.model}"
                if self.router.should_fallback(exc) and self._retry_counts.get(key, 0) < 1:
                    self._retry_counts[key] = self._retry_counts.get(key, 0) + 1
                    await asyncio.sleep(0.25)
                    # Same target, one retry: refresh the reported route so the
                    # UI never shows a stale model after the retry succeeds.
                    self.last_route = {"provider_id": target.provider_id, "model": target.model}
                    continue
                next_target = self.router.next_fallback(target)
                if next_target is None:
                    raise
                self.last_route = {"provider_id": next_target.provider_id, "model": next_target.model}
                target = next_target
