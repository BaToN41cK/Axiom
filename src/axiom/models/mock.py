"""MockProvider for tests and offline development (explicitly a test double)."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from axiom.models.provider import ChatResponse, ModelProvider, StreamChunk, ToolSpec, Usage


class MockProvider(ModelProvider):
    """Deterministic scripted provider for tests.

    A MockProvider is an explicit test double, NOT a fake shipped feature:
    it is never used by the TUI/CLI unless the user configures mock provider.
    """

    name = "mock"

    def __init__(self, model: str = "mock-model", script: list[dict[str, Any]] | None = None) -> None:
        self.model_name = model
        self.supports_streaming = True
        self.supports_tools = True
        self._script = list(script or [])
        self._calls: list[list[dict[str, Any]]] = []

    def queue(self, response: dict[str, Any]) -> None:
        """Queue a scripted response: {'content': str} and/or {'tool_calls': [...]}."""
        self._script.append(response)

    @property
    def calls(self) -> list[list[dict[str, Any]]]:
        return self._calls

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> ChatResponse:
        self._calls.append([dict(m) for m in messages])
        if self._script:
            item = self._script.pop(0)
        else:
            item = {"content": "Task complete."}
        tool_calls = [
            {"id": tc.get("id", f"call_{i}"), "name": tc["name"], "arguments": tc.get("arguments", {})}
            for i, tc in enumerate(item.get("tool_calls", []))
        ]
        if tool_calls and item.get("content") is None:
            item["content"] = ""
        return ChatResponse(
            content=item.get("content", ""),
            tool_calls=tool_calls,
            usage=Usage(input_tokens=100, output_tokens=10, tokens_per_second=50.0),
            model=self.model_name,
            finish_reason="tool_calls" if tool_calls else "stop",
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        response = await self.chat(messages, tools, temperature, max_tokens, system)
        for word in response.content.split(" "):
            if word:
                yield StreamChunk(delta=word + " ")
        if response.tool_calls:
            yield StreamChunk(tool_calls=response.tool_calls, finish_reason="tool_calls")
        yield StreamChunk(
            finish_reason="stop",
            usage=Usage(input_tokens=100, output_tokens=10, tokens_per_second=50.0),
        )

    async def validate(self) -> bool:
        return True
