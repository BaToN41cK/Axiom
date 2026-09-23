"""Единый интерфейс провайдера: AXIOM -> Provider -> Model.

Агент никогда не ветвится по вендорам — только эти методы.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProviderStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ProviderCapabilities:
    tools: bool = False
    reasoning: bool = False
    vision: bool = False
    prompt_cache: bool = False
    streaming: bool = True
    long_context: bool = False


@dataclass
class ModelProfile:
    id: str
    provider_id: str
    display_name: str = ""
    coding: bool = False
    reasoning: bool = False
    tool_calling: bool = False
    long_context: bool = False
    vision: bool = False
    context_length: int | None = None

    def label(self) -> str:
        return self.display_name or self.id


@dataclass
class ChatMessage:
    role: str
    content: str
    images: list[str] = field(default_factory=list)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamChunk:
    thinking: str = ""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    done: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None


@dataclass
class ChatResult:
    content: str = ""
    thinking: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


class ProviderError(Exception):
    kind: str = "provider_error"

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class ProviderAuthError(ProviderError):
    kind = "provider_auth"


class ProviderUnavailableError(ProviderError):
    kind = "provider_unavailable"


class Provider:
    """Единый интерфейс. Новый API = новый адаптер, а не правка Core."""

    id: str = "base"
    label: str = "Base"

    async def authenticate(self) -> ProviderStatus:
        raise NotImplementedError

    async def list_models(self) -> list[ModelProfile]:
        raise NotImplementedError

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        think: bool | str | None = None,
        options: dict[str, Any] | None = None,
    ) -> ChatResult:
        raise NotImplementedError

    def stream(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        think: bool | str | None = None,
        options: dict[str, Any] | None = None,
    ):
        raise NotImplementedError

    def supports_tools(self, model: str | None = None) -> bool | None:
        return None

    def supports_reasoning(self, model: str | None = None) -> bool | None:
        return None

    def supports_vision(self, model: str | None = None) -> bool | None:
        return None

    def supports_prompt_cache(self, model: str | None = None) -> bool | None:
        return None

    def capabilities(self, model: str | None = None) -> ProviderCapabilities:
        return ProviderCapabilities()
