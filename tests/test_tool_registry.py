"""Tests for tool registry."""

from __future__ import annotations

import pytest

from axiom.core.types import ToolCall, ToolResult
from axiom.permissions.manager import PermissionManager
from axiom.tools.registry import ToolRegistry, ToolContext


@pytest.fixture
def tool_registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def tool_context(tmp_path) -> ToolContext:
    import os
    return ToolContext(
        workspace=str(tmp_path),
        permission_manager=PermissionManager(
            config={"test.permission": "allow"}
        ),
        config={},
    )


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_tool(self, tool_registry: ToolRegistry) -> None:
        async def handler(**kwargs):
            return ToolResult(tool_call_id="", name="test", content="ok")

        tool_registry.register(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            permission="test.permission",
        )

        assert "test_tool" in tool_registry
        assert tool_registry.get("test_tool") is not None

    def test_unregister_tool(self, tool_registry: ToolRegistry) -> None:
        async def handler(**kwargs):
            return ToolResult(tool_call_id="", name="test", content="ok")

        tool_registry.register(
            name="test_tool",
            description="Test",
            parameters={},
            handler=handler,
        )
        tool_registry.unregister("test_tool")
        assert "test_tool" not in tool_registry

    def test_list_tools(self, tool_registry: ToolRegistry) -> None:
        async def handler(**kwargs):
            return ToolResult(tool_call_id="", name="test", content="ok")

        tool_registry.register(
            name="tool1",
            description="Tool 1",
            parameters={},
            handler=handler,
        )
        tool_registry.register(
            name="tool2",
            description="Tool 2",
            parameters={},
            handler=handler,
        )

        tools = tool_registry.list_tools()
        assert len(tools) == 2

    @pytest.mark.asyncio
    async def test_execute_tool(self, tool_registry: ToolRegistry, tool_context: ToolContext) -> None:
        async def handler(**kwargs):
            return ToolResult(tool_call_id="", name="test", content="success")

        tool_registry.register(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            permission="test.permission",
        )

        call = ToolCall(id="call_1", name="test_tool", arguments={})
        result = await tool_registry.execute(call, tool_context)

        assert result.is_error is False
        assert result.content == "success"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, tool_registry: ToolRegistry, tool_context: ToolContext) -> None:
        call = ToolCall(id="call_1", name="nonexistent", arguments={})
        result = await tool_registry.execute(call, tool_context)

        assert result.is_error is True
        assert "unknown tool" in result.content.lower()

    @pytest.mark.asyncio
    async def test_execute_permission_denied(self, tool_registry: ToolRegistry, tool_context: ToolContext) -> None:
        async def handler(**kwargs):
            return ToolResult(tool_call_id="", name="test", content="should not run")

        pm = PermissionManager(config={"test.denied": "deny"})
        ctx = ToolContext(
            workspace=tool_context.workspace,
            permission_manager=pm,
            config={},
        )

        tool_registry.register(
            name="denied_tool",
            description="Denied tool",
            parameters={},
            handler=handler,
            permission="test.denied",
        )

        call = ToolCall(id="call_1", name="denied_tool", arguments={})
        result = await tool_registry.execute(call, ctx)

        assert result.is_error is True
        assert "denied" in result.content.lower()

    @pytest.mark.asyncio
    async def test_execute_tool_error(self, tool_registry: ToolRegistry, tool_context: ToolContext) -> None:
        async def handler(**kwargs):
            raise RuntimeError("Tool exploded")

        tool_registry.register(
            name="error_tool",
            description="Error tool",
            parameters={},
            handler=handler,
            permission="test.permission",
        )

        call = ToolCall(id="call_1", name="error_tool", arguments={})
        result = await tool_registry.execute(call, tool_context)

        assert result.is_error is True
        assert "error" in result.content.lower()
