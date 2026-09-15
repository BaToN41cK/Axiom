"""Tool registry permission / failure tests."""

from __future__ import annotations

from axiom.core.errors import AxiomError
from axiom.core.tools.base import ToolDefinition, ToolPermission, ToolResult
from axiom.core.tools.registry import ToolRegistry


async def ok_handler(**kwargs) -> ToolResult:
    return ToolResult(name="?", ok=True, content="done")


async def test_never_permission_tool_is_blocked_and_hidden():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(name="danger", description="d", permission=ToolPermission.NEVER),
        ok_handler,
    )
    result = await registry.execute("danger", {})
    assert result.ok is False
    assert "disabled" in (result.error or "")
    assert registry.definitions() == []
    assert registry.schemas() == []


async def test_unknown_tool_returns_structured_error():
    registry = ToolRegistry()
    result = await registry.execute("nope", {"a": 1})
    assert result.ok is False
    assert "Unknown tool" in (result.error or "")


async def test_handler_axiom_error_becomes_tool_error():
    async def failing(**kwargs) -> ToolResult:
        raise AxiomError("backend down")

    registry = ToolRegistry()
    registry.register(ToolDefinition(name="t", description="d"), failing)
    result = await registry.execute("t", {})
    assert result.ok is False
    assert result.error == "backend down"


async def test_handler_crash_never_propagates():
    async def crashing(**kwargs) -> ToolResult:
        raise RuntimeError("boom")

    registry = ToolRegistry()
    registry.register(ToolDefinition(name="t", description="d"), crashing)
    result = await registry.execute("t", {})
    assert result.ok is False
    assert "RuntimeError" in (result.error or "")


async def test_invalid_arguments_reported():
    async def strict(*, required: str) -> ToolResult:
        return ToolResult(name="t", ok=True, content=required)

    registry = ToolRegistry()
    registry.register(ToolDefinition(name="t", description="d"), strict)
    result = await registry.execute("t", {})
    assert result.ok is False
    assert "Invalid arguments" in (result.error or "")
