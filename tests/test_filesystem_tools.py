"""Tests for filesystem tools."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from axiom.core.errors import WorkspaceBoundaryError
from axiom.tools.filesystem import (
    read_file,
    write_file,
    edit_file,
    delete_file,
    list_directory,
    _resolve_path,
)
from axiom.tools.registry import ToolContext


@pytest.fixture
def temp_workspace(tmp_path: Path) -> str:
    return str(tmp_path)


@pytest.fixture
def tool_context(temp_workspace: str) -> ToolContext:
    from axiom.permissions.manager import PermissionManager
    return ToolContext(
        workspace=temp_workspace,
        permission_manager=PermissionManager(
            config={
                "filesystem.read": "allow",
                "filesystem.write": "allow",
                "filesystem.delete": "allow",
            }
        ),
        config={"ignore_patterns": [".git", "__pycache__"]},
    )


class TestResolvePath:
    def test_relative_path(self, temp_workspace: str) -> None:
        result = _resolve_path("test.txt", temp_workspace)
        assert result == Path(temp_workspace) / "test.txt"

    def test_nested_relative_path(self, temp_workspace: str) -> None:
        result = _resolve_path("subdir/test.txt", temp_workspace)
        assert result == Path(temp_workspace) / "subdir" / "test.txt"

    def test_path_traversal_blocked(self, temp_workspace: str) -> None:
        with pytest.raises(WorkspaceBoundaryError):
            _resolve_path("../../../etc/passwd", temp_workspace)

    def test_outside_workspace_blocked(self, temp_workspace: str) -> None:
        with pytest.raises(WorkspaceBoundaryError):
            _resolve_path("/tmp/outside.txt", temp_workspace)



class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tool_context: ToolContext, temp_workspace: str) -> None:
        test_file = Path(temp_workspace) / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")

        result = await read_file(path="test.txt", _context=tool_context)
        assert result.is_error is False
        assert result.content == "Hello, World!"

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tool_context: ToolContext) -> None:
        result = await read_file(path="nonexistent.txt", _context=tool_context)
        assert result.is_error is True
        assert "not found" in result.content.lower()

    @pytest.mark.asyncio
    async def test_read_with_offset(self, tool_context: ToolContext, temp_workspace: str) -> None:
        test_file = Path(temp_workspace) / "test.txt"
        test_file.write_text("line1\nline2\nline3", encoding="utf-8")

        result = await read_file(path="test.txt", offset=2, _context=tool_context)
        assert "line2" in result.content
        assert "line1" not in result.content

    @pytest.mark.asyncio
    async def test_read_outside_workspace(self, tool_context: ToolContext) -> None:
        result = await read_file(path="/tmp/secret.txt", _context=tool_context)
        assert result.is_error is True
        assert "outside workspace" in result.content.lower()


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tool_context: ToolContext, temp_workspace: str) -> None:
        result = await write_file(path="new.txt", content="test content", _context=tool_context)
        assert result.is_error is False

        written = Path(temp_workspace) / "new.txt"
        assert written.exists()
        assert written.read_text(encoding="utf-8") == "test content"

    @pytest.mark.asyncio
    async def test_write_creates_directories(self, tool_context: ToolContext, temp_workspace: str) -> None:
        result = await write_file(
            path="subdir/deeper/file.txt",
            content="nested content",
            _context=tool_context,
        )
        assert result.is_error is False

        written = Path(temp_workspace) / "subdir" / "deeper" / "file.txt"
        assert written.exists()

    @pytest.mark.asyncio
    async def test_write_outside_workspace(self, tool_context: ToolContext) -> None:
        result = await write_file(path="/tmp/secret.txt", content="data", _context=tool_context)
        assert result.is_error is True


class TestEditFile:
    @pytest.mark.asyncio
    async def test_edit_existing_text(self, tool_context: ToolContext, temp_workspace: str) -> None:
        test_file = Path(temp_workspace) / "test.txt"
        test_file.write_text("Hello World!", encoding="utf-8")

        result = await edit_file(
            path="test.txt",
            old_text="World",
            new_text="Axiom",
            _context=tool_context,
        )
        assert result.is_error is False
        assert test_file.read_text(encoding="utf-8") == "Hello Axiom!"

    @pytest.mark.asyncio
    async def test_edit_text_not_found(self, tool_context: ToolContext, temp_workspace: str) -> None:
        test_file = Path(temp_workspace) / "test.txt"
        test_file.write_text("Hello World!", encoding="utf-8")

        result = await edit_file(
            path="test.txt",
            old_text="nonexistent",
            new_text="replacement",
            _context=tool_context,
        )
        assert result.is_error is True
        assert "not found" in result.content.lower()


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_delete_file(self, tool_context: ToolContext, temp_workspace: str) -> None:
        test_file = Path(temp_workspace) / "test.txt"
        test_file.write_text("delete me", encoding="utf-8")

        result = await delete_file(path="test.txt", _context=tool_context)
        assert result.is_error is False
        assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tool_context: ToolContext) -> None:
        result = await delete_file(path="nonexistent.txt", _context=tool_context)
        assert result.is_error is True


class TestListDirectory:
    @pytest.mark.asyncio
    async def test_list_empty_directory(self, tool_context: ToolContext) -> None:
        result = await list_directory(path=".", _context=tool_context)
        assert result.is_error is False
        assert "empty" in result.content.lower()

    @pytest.mark.asyncio
    async def test_list_with_files(self, tool_context: ToolContext, temp_workspace: str) -> None:
        (Path(temp_workspace) / "file1.txt").write_text("a")
        (Path(temp_workspace) / "file2.txt").write_text("b")

        result = await list_directory(path=".", _context=tool_context)
        assert result.is_error is False
        assert "file1.txt" in result.content
        assert "file2.txt" in result.content
