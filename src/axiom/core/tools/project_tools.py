"""Project tools — open/switch/inspect/create the current workspace.

The GUI calls these through ``ChatSession`` directly; the agent gets the
read-only ``inspect_project`` tool so it can ground itself in the real
directory (§4) without ever changing the session behind the user's back.
"""

from __future__ import annotations

from pathlib import Path

from axiom.core.tools.base import ToolDefinition, ToolPermission, ToolResult
from axiom.core.tools.filesystem import default_workspace_root

INSPECT_PROJECT_TOOL = "inspect_project"

PROJECT_TOOLS = (INSPECT_PROJECT_TOOL,)


class ProjectTools:
    """Read-only project inspection rooted at the workspace root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_workspace_root()).resolve()

    def set_root(self, root: Path) -> None:
        self.root = root.resolve()

    def register(self, registry) -> None:
        registry.register(
            ToolDefinition(
                name=INSPECT_PROJECT_TOOL,
                description=(
                    "Describe the current workspace: absolute path, detected "
                    "project kind, git branch and top-level entries."
                ),
                parameters={"type": "object", "properties": {}, "required": []},
                permission=ToolPermission.ALWAYS,
            ),
            self._inspect,
        )

    async def _inspect(self) -> ToolResult:
        from axiom.core.workspace import detect_project

        info = detect_project(self.root)
        lines = [
            f"Path: {info.path}",
            f"Project: {info.name}",
            f"Type: {info.kind}",
            f"Git: {'yes' + (f' ({info.branch})' if info.branch else '') if info.git else 'no'}",
        ]
        if info.entries:
            lines.append("Top-level: " + ", ".join(info.entries))
        return ToolResult(name=INSPECT_PROJECT_TOOL, ok=True, content="\n".join(lines))
