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


async def test_read_file_line_range_and_numbers(ws: WorkspaceTools) -> None:
    body = "\n".join(f"line{i}" for i in range(1, 11)) + "\n"
    await ws._write_file(path="big.txt", content=body)

    ranged = await ws._read_file(path="big.txt", start_line=3, end_line=5)
    assert ranged.ok
    assert "lines 3-5 of 10" in ranged.content
    assert "line3" in ranged.content and "line5" in ranged.content
    assert "line2" not in ranged.content and "line6" not in ranged.content

    numbered = await ws._read_file(path="big.txt", start_line=3, end_line=3, line_numbers=True)
    assert numbered.ok and "3\tline3" in numbered.content

    past = await ws._read_file(path="big.txt", start_line=99)
    assert not past.ok and "past the end" in (past.error or "")

    inverted = await ws._read_file(path="big.txt", start_line=5, end_line=2)
    assert not inverted.ok and "before start_line" in (inverted.error or "")


async def test_read_file_rejects_binary_content(ws: WorkspaceTools) -> None:
    (ws.root / "blob.dat").write_bytes(b"PK\x00\x03\x04binary\x00data")
    result = await ws._read_file(path="blob.dat")
    assert not result.ok and "binary" in (result.error or "")


async def test_write_and_edit_dry_run_do_not_touch_disk(ws: WorkspaceTools) -> None:
    preview = await ws._write_file(path="ghost.py", content="x = 1\n", dry_run=True)
    assert preview.ok and "Would create" in preview.content
    assert not (ws.root / "ghost.py").exists()
    assert preview.data and preview.data["dry_run"] is True

    await ws._write_file(path="real.py", content="x = 1\n")
    dry = await ws._edit_file(path="real.py", old_text="x = 1", new_text="x = 2", dry_run=True)
    assert dry.ok and "Dry run" in dry.content
    assert (ws.root / "real.py").read_text(encoding="utf-8") == "x = 1\n"

    real = await ws._edit_file(path="real.py", old_text="x = 1", new_text="x = 2")
    assert real.ok and "--- a/real.py" in real.content
    assert (ws.root / "real.py").read_text(encoding="utf-8") == "x = 2\n"
    assert real.data and real.data["diff"]


async def test_search_text_regex_context_and_path_filter(ws: WorkspaceTools) -> None:
    (ws.root / "pkg").mkdir()
    (ws.root / "pkg" / "a.py").write_text("def alpha():\n    return 1\ndef beta():\n", encoding="utf-8")
    (ws.root / "pkg" / "notes.md").write_text("plain text here\n", encoding="utf-8")

    regex_hit = await ws._search_text(query=r"def \w+\(", regex=True, glob="*.py")
    assert regex_hit.ok and "pkg/a.py:1" in regex_hit.content

    invalid = await ws._search_text(query="[unclosed", regex=True)
    assert not invalid.ok and "Invalid regex" in (invalid.error or "")

    ctx = await ws._search_text(query="return 1", context=1, path="pkg")
    assert ctx.ok and ">2:" in ctx.content

    outside = await ws._search_text(query="def", path="nope")
    assert not outside.ok

    scoped = await ws._search_files(pattern="*.py", path="pkg")
    assert scoped.ok and "pkg/a.py" in scoped.content


async def test_apply_patch_valid_dry_run_and_reject(ws: WorkspaceTools) -> None:
    await ws._write_file(path="cfg.py", content="alpha\nbeta\ngamma\n")

    patch = "--- a/cfg.py\n+++ b/cfg.py\n@@ -1,3 +1,3 @@\n alpha\n-beta\n+BETA\n gamma\n"
    dry = await ws._apply_patch(path="cfg.py", patch=patch, dry_run=True)
    assert dry.ok and "Dry run" in dry.content
    assert (ws.root / "cfg.py").read_text(encoding="utf-8") == "alpha\nbeta\ngamma\n"

    applied = await ws._apply_patch(path="cfg.py", patch=patch)
    assert applied.ok and "+1 -1" in applied.content
    assert (ws.root / "cfg.py").read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"
    assert applied.data and applied.data["added"] == 1 and applied.data["removed"] == 1

    broken = await ws._apply_patch(
        path="cfg.py",
        patch="--- a/cfg.py\n+++ b/cfg.py\n@@ -1,3 +1,3 @@\n alpha\n-WRONG\n+X\n gamma\n",
    )
    assert not broken.ok and "nothing written" in (broken.error or "")
    assert (ws.root / "cfg.py").read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"

    empty = await ws._apply_patch(path="cfg.py", patch="   ")
    assert not empty.ok and "empty" in (empty.error or "").lower()


async def test_apply_patch_creates_missing_file_via_full_hunk(ws: WorkspaceTools) -> None:
    patch = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n+one\n+two\n"
    result = await ws._apply_patch(path="new.py", patch=patch)
    assert result.ok and result.data and result.data["created"] is True
    # The patch itself carries no trailing newline after the last line.
    assert (ws.root / "new.py").read_text(encoding="utf-8") == "one\ntwo"
