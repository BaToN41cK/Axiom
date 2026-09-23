"""Tool registry permission / failure tests."""

from __future__ import annotations

from axiom.core.errors import AxiomError
from axiom.core.tools.base import ToolDefinition, ToolPermission, ToolResult
from axiom.core.tools.registry import ToolRegistry


async def ok_handler(**kwargs) -> ToolResult:
    return ToolResult(name="?", ok=True, content="done")


async def test_subset_clones_bound_handler_owner_and_tool_definition():
    class _Handler:
        def __init__(self, root: str) -> None:
            self.root = root

        async def run(self) -> ToolResult:
            return ToolResult(name="root", ok=True, content=self.root)

    handler = _Handler("original")
    registry = ToolRegistry()
    definition = ToolDefinition(name="root", description="root")
    registry.register(definition, handler.run)

    subset = registry.subset(["root"])
    cloned_definition = subset.get("root")
    cloned_handler = subset._tools["root"][1]
    assert cloned_definition is not definition
    assert cloned_handler.__self__ is not handler
    assert cloned_handler.__self__.root == "original"
    cloned_handler.__self__.root = "request-only"
    assert handler.root == "original"
    subset.unregister("root")
    assert registry.get("root") is definition


async def test_subset_clones_terminal_permission_classifier_owner():
    from axiom.core.tools.terminal import TerminalTool

    terminal = TerminalTool(enabled=True)
    registry = ToolRegistry()
    terminal.register(registry)
    subset = registry.subset(["run_command"])
    cloned_handler = subset._tools["run_command"][1]
    cloned_classifier = subset.classifier["run_command"]

    assert cloned_handler.__self__ is cloned_classifier.__self__
    cloned_classifier.__self__.enabled = False
    assert registry.classifier["run_command"]("run_command", {"command": "git status"}) \
        is ToolPermission.ALWAYS
    assert cloned_classifier("run_command", {"command": "git status"}) is ToolPermission.NEVER


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
