"""Model provider abstraction: base types and interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from axiom.core.types import HealthStatus


@dataclass
class ToolSpec:
    """OpenAI-style tool definition sent to the model."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Description of a model."""

    id: str
    provider: str
    display_name: str = ""
    context_window: int = 32_768
    max_output_tokens: int = 4096
    reasoning: bool = False
    vision: bool = False
    tool_calling: bool = True
    streaming: bool = True
    speed: float = 1.0  # relative tokens/sec score
    priority: int = 50
    availability: HealthStatus = HealthStatus.OFFLINE
    task_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.id


@dataclass
class ProviderInfo:
    """Description of a provider."""

    name: str
    display_name: str = ""
    base_url: str = ""
    requires_api_key: bool = True
    health: HealthStatus = HealthStatus.OFFLINE
    models: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.name


@dataclass
class Usage:
    """Token usage stats for a response."""

    input_tokens: int = 0
    output_tokens: int = 0
    tokens_per_second: float = 0.0


@dataclass
class ChatResponse:
    """Full (non-streaming) model response."""

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""


@dataclass
class StreamChunk:
    """Incremental piece of a streamed response."""

    delta: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: Usage | None = None


class ModelProvider(ABC):
    """Base class for all model providers (adapter architecture)."""

    name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Send a chat completion request."""

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion."""

    @abstractmethod
    async def validate(self) -> bool:
        """Check provider connectivity/credentials."""

