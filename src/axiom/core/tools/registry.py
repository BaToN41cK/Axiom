"""Tool registry — the single place where agent tools are declared.

Tools are never executed silently: each one carries an explicit
:class:`~axiom.core.tools.base.ToolPermission`. Adding a tool requires no UI
changes — frontends render :class:`~axiom.core.events.ToolCallEvent` and
:class:`~axiom.core.events.ToolResultEvent` generically.
"""

from __future__ import annotations

import time

from axiom.core.errors import AxiomError
from axiom.core.tools.base import (
    ToolDefinition,
    ToolHandler,
    ToolPermission,
    ToolResult,
)


class ToolRegistry:
    """Holds tool definitions together with their real handlers."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolDefinition, ToolHandler]] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        self._tools[definition.name] = (definition, handler)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> ToolDefinition | None:
        entry = self._tools.get(name)
        return entry[0] if entry else None

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def definitions(self, *, allowed: ToolPermission | None = None) -> list[ToolDefinition]:
        """Tool definitions suitable for the model request."""
        result = []
        for definition, _ in self._tools.values():
            if definition.permission is ToolPermission.NEVER:
                continue
            if allowed is not None and definition.permission is not allowed:
                continue
            result.append(definition)
        return result

    def schemas(self) -> list[dict]:
        """Tool schemas for the Ollama ``tools`` parameter."""
        return [d.schema() for d in self.definitions()]

    async def execute(self, name: str, arguments: dict | None = None) -> ToolResult:
        """Execute a tool by name, enforcing its permission.

        A model can never force execution of a ``NEVER`` tool, and unknown
        tools fail with a structured result instead of raising.
        """
        started = time.perf_counter()
        entry = self._tools.get(name)
        if entry is None:
            return ToolResult(name=name, ok=False, error=f"Unknown tool: {name}")
        definition, handler = entry
        if definition.permission is ToolPermission.NEVER:
            return ToolResult(name=name, ok=False, error=f"Tool '{name}' is disabled")
        try:
            result = await handler(**(arguments or {}))
        except AxiomError as exc:
            result = ToolResult(name=name, ok=False, error=str(exc))
        except TypeError as exc:
            result = ToolResult(name=name, ok=False, error=f"Invalid arguments: {exc}")
        except Exception as exc:
            result = ToolResult(name=name, ok=False, error=f"{type(exc).__name__}: {exc}")
        result.name = name
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        return result
