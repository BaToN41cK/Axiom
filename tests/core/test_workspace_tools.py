"""Tests for the sandboxed workspace filesystem tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from axiom.core.tools.filesystem import WorkspaceTools
from axiom.core.tools.registry import ToolRegistry


@pytest.fixture()
def ws(tmp_path: Path) -> WorkspaceTools:
    return WorkspaceTools(tmp_path)


async def test_sandbox_rejects_escape(ws: WorkspaceTools) -> None:
    with pytest.raises(ValueError, match="outside the workspace"):
        ws.resolve("../outside.txt")
    with pytest.raises(ValueError, match="outside the workspace"):
        ws.resolve(str(Path("C:/Windows/system32")))


async def test_list_and_read(ws: WorkspaceTools) -> None:
    (ws.root / "sub").mkdir()
    (ws.root / "sub" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    listed = await ws._list_files(path=".")
    assert listed.ok and "sub/" in listed.content
    read = await ws._read_file(path="sub/app.py")
    assert read.ok and "print('hi')" in read.content
    missing = await ws._read_file(path="sub/nope.py")
    assert not missing.ok


async def test_write_and_edit(ws: WorkspaceTools) -> None:
    created = await ws._write_file(path="new/mod.py", content="x = 1\n")
    assert created.ok and "Created" in created.content
    edited = await ws._edit_file(path="new/mod.py", old_text="x = 1", new_text="x = 2")
    assert edited.ok
    assert (ws.root / "new" / "mod.py").read_text(encoding="utf-8") == "x = 2\n"


async def test_edit_requires_unique_match(ws: WorkspaceTools) -> None:
    await ws._write_file(path="dup.py", content="same\nsame\n")
    bad = await ws._edit_file(path="dup.py", old_text="same", new_text="other")
    assert not bad.ok and "matches 2" in (bad.error or "")
    absent = await ws._edit_file(path="dup.py", old_text="zzz", new_text="y")
    assert not absent.ok and "not found" in (absent.error or "")


async def test_registry_roundtrip(ws: WorkspaceTools) -> None:
    registry = ToolRegistry()
    ws.register(registry)
    for name in ("list_files", "read_file", "write_file", "edit_file"):
        assert registry.get(name) is not None
    result = await registry.execute("read_file", {"path": "missing.txt"})
    assert not result.ok
