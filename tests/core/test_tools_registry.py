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


async def test_tool_definition_metadata_defaults_and_schema_shape():
    definition = ToolDefinition(name="t", description="d")
    meta = definition.meta()
    assert meta["risk"] == "safe"
    assert meta["timeout"] is None
    assert meta["max_output"] is None
    assert meta["streaming"] is False
    assert meta["cancellable"] is True
    assert meta["dry_run"] is False
    assert meta["rollback"] == "none"
    assert meta["workspace_scoped"] is False
    # The model-facing schema must stay the plain OpenAI/Ollama shape.
    schema = definition.schema()
    assert set(schema["function"]) == {"name", "description", "parameters"}


async def test_registered_tools_carry_risk_metadata():
    from axiom.core.tools.filesystem import WorkspaceTools
    from axiom.core.tools.git_tools import GitTools
    from axiom.core.tools.terminal import TerminalTool

    registry = ToolRegistry()
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        WorkspaceTools(root).register(registry)
        GitTools(root).register(registry)
        TerminalTool(root=root, enabled=True).register(registry)

        read = registry.get("read_file")
        write = registry.get("write_file")
        delete = registry.get("delete_file")
        command = registry.get("run_command")
        status = registry.get("git_status")

    assert read is not None and read.risk == "safe" and read.workspace_scoped is True
    assert write is not None and write.risk == "medium" and write.dry_run is True
    assert write is not None and write.rollback == "checkpoint"
    assert delete is not None and delete.risk == "dangerous"
    assert command is not None and command.risk == "dangerous"
    assert command.max_output is not None and command.timeout is not None
    assert status is not None and status.risk == "safe" and status.timeout is not None
