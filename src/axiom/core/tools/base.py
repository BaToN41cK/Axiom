from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class ToolPermission(str, Enum):
    """How a tool may be executed.

    ``ALWAYS``  — safe, executed automatically.
    ``ASK``     — requires explicit user approval (future permission UI).
    ``NEVER``   — disabled.
    """

    ALWAYS = "always"
    ASK = "ask"
    NEVER = "never"


@dataclass
class ToolDefinition:
    """Declarative description of a tool handed to the model."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    permission: ToolPermission = ToolPermission.ASK

    def schema(self) -> dict[str, Any]:
        """Ollama/OpenAI-compatible tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
                or {"type": "object", "properties": {}, "required": []},
            },
        }


@dataclass
class ToolResult:
    """Structured result of a real tool execution."""

    name: str
    ok: bool
    content: str = ""
    error: str | None = None
    duration_ms: int = 0
    data: Any = None


ToolHandler = Callable[..., Awaitable[ToolResult]]