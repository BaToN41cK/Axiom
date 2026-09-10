"""Tool registry: definition, lookup and permission-checked execution."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from axiom.core.errors import ToolTimeoutError
from axiom.core.logging import get_logger
from axiom.core.types import ToolCall, ToolResult
from axiom.permissions.manager import PermissionManager, PermissionRequest

logger = get_logger("tools")

Handler = Callable[..., Awaitable[ToolResult]]


@dataclass
class ToolContext:
    """Context handed to every tool invocation."""

    workspace: str
    permission_manager: PermissionManager
    config: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    emit: Callable[[str, dict[str, Any]], None] | None = None


@dataclass
class ToolSpec:
    """Definition of a tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler
    permission: str = ""
    timeout: float = 60.0
    readonly: bool = False

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }


def _filter_kwargs(handler: Handler, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Pass only kwargs accepted by the handler signature."""
    sig = inspect.signature(handler)
    accepts_var = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if accepts_var:
        return kwargs
    allowed = set(sig.parameters)
    return {k: v for k, v in kwargs.items() if k in allowed}


class ToolRegistry:
    """Registry of tools with permission-checked async execution."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # -- management ------------------------------------------------------
    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        handler: Handler | None = None,
        permission: str = "",
        timeout: float = 60.0,
        readonly: bool = False,
    ) -> None:
        if handler is None:
            raise ValueError(f"Tool '{name}' requires a handler")
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}},
            handler=handler,
            permission=permission,
            timeout=timeout,
            readonly=readonly,
        )

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        return sorted(self._tools)

    def to_openai_tools(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        tools = self._tools.values()
        if names is not None:
            tools = [t for t in tools if t.name in names]
        return [t.to_openai_schema() for t in tools]

    # -- execution -------------------------------------------------------
    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        spec = self._tools.get(call.name)
        if spec is None:
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=f"Error: unknown tool '{call.name}'. "
                f"Available: {', '.join(self.list_names())}",
                is_error=True,
            )

        if spec.permission:
            response = await context.permission_manager.check(
                PermissionRequest(
                    permission=spec.permission,
                    action=call.name,
                    detail=self._describe(call),
                    metadata={"arguments": call.arguments},
                )
            )
            if not response.allowed:
                return ToolResult(
                    tool_call_id=call.id,
                    name=call.name,
                    content=f"Error: permission denied for '{call.name}' "
                    f"(permission: {spec.permission}).",
                    is_error=True,
                )

        if context.emit:
            try:
                context.emit("tool_start", {"name": call.name, "arguments": call.arguments})
            except Exception:  # noqa: BLE001
                pass

        result = await self._run(spec, call, context)

        if context.emit:
            try:
                context.emit("tool_end", {"name": call.name, "is_error": result.is_error})
            except Exception:  # noqa: BLE001
                pass
        return result

    async def _run(self, spec: ToolSpec, call: ToolCall, context: ToolContext) -> ToolResult:
        try:
            kwargs = _filter_kwargs(spec.handler, dict(call.arguments))
            return await asyncio.wait_for(
                spec.handler(**kwargs, _context=context),
                timeout=spec.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool timeout: %s", call.name)
            return ToolResult(
                tool_call_id=call.id,
                name=call.name,
                content=f"Error: tool '{call.name}' timed out after {spec.timeout}s.",
                is_error=True,
            )
        except ToolTimeoutError as exc:
            return ToolResult(tool_call_id=call.id, name=call.name, content=str(exc), is_error=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tool error %s: %s", call.name, exc)
            return ToolResult(
                tool_call_id=call.id, name=call.name, content=f"Error: {exc}", is_error=True
            )

    @staticmethod
    def _describe(call: ToolCall) -> str:
        try:
            args = json.dumps(call.arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            args = str(call.arguments)
        return f"{call.name} {args}"[:300]
