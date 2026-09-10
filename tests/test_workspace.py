"""Workspace boundary / security tests (Windows-focused)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from axiom.core.errors import WorkspaceBoundaryError
from axiom.permissions.sandbox import is_path_inside_workspace, validate_workspace_path


@pytest.fixture
def workspace(tmp_path: Path) -> str:
    return str(tmp_path)


class TestWorkspaceBoundary:
    def test_relative_path_ok(self, workspace: str) -> None:
        assert validate_workspace_path("sub/file.txt", workspace).is_absolute()

    def test_traversal_blocked(self, workspace: str) -> None:
        with pytest.raises(WorkspaceBoundaryError):
            validate_workspace_path("..\\..\\outside.txt", workspace)

    def test_mixed_traversal_blocked(self, workspace: str) -> None:
        with pytest.raises(WorkspaceBoundaryError):
            validate_workspace_path("sub/../../..", workspace)

    def test_absolute_outside_blocked(self, workspace: str) -> None:
        with pytest.raises(WorkspaceBoundaryError):
            validate_workspace_path("C:\\Windows\\system32\\config", workspace)

    def test_workspace_itself_ok(self, workspace: str) -> None:
        assert validate_workspace_path(".", workspace) == Path(workspace).resolve()

    def test_symlink_escape_blocked(self, workspace: str, tmp_path: Path) -> None:
        link = Path(workspace) / "evil"
        target = tmp_path / "outside"
        target.mkdir()
        try:
            os.symlink(target, link)
        except OSError:
            pytest.skip("symlink not permitted")
        with pytest.raises(WorkspaceBoundaryError):
            validate_workspace_path("evil/file.txt", workspace)

    def test_is_path_inside(self, workspace: str) -> None:
        assert is_path_inside_workspace("ok.txt", workspace)
        assert not is_path_inside_workspace("../x", workspace)

    def test_empty_path_returns_workspace(self, workspace: str) -> None:
        assert validate_workspace_path("", workspace) == Path(workspace).resolve()


class TestTerminalSecurity:
    def test_blocked_command(self) -> None:
        from axiom.permissions.rules import is_blocked_command

        assert is_blocked_command("format c: /q")
        assert is_blocked_command("rm -rf / --no-preserve-root")
        assert not is_blocked_command("python -m pytest")

    def test_readonly_derivation(self) -> None:
        from axiom.permissions.rules import derive_permission_for_command

        assert derive_permission_for_command("git status") == "terminal.execute.readonly"
        assert derive_permission_for_command("npm install something") == "terminal.execute"

    @pytest.mark.asyncio
    async def test_execute_command_blocked(self, tmp_path: Path) -> None:
        from axiom.permissions.manager import PermissionManager
        from axiom.tools.terminal import execute_command
        from axiom.tools.registry import ToolContext

        ctx = ToolContext(
            workspace=str(tmp_path),
            permission_manager=PermissionManager(config={"terminal.execute": "allow"}),
            config={},
        )
        result = await execute_command(command="format c:", _context=ctx)
        assert result.is_error
        assert "blocked" in result.content

    @pytest.mark.asyncio
    async def test_execute_command_runs(self, tmp_path: Path) -> None:
        from axiom.permissions.manager import PermissionManager
        from axiom.tools.terminal import execute_command
        from axiom.tools.registry import ToolContext

        ctx = ToolContext(
            workspace=str(tmp_path),
            permission_manager=PermissionManager(config={"terminal.execute": "allow"}),
            config={},
        )
        result = await execute_command(command="echo axiom_ok", _context=ctx)
        assert "axiom_ok" in result.content
