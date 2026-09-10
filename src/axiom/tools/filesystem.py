"""Filesystem tools with workspace boundary enforcement."""

from __future__ import annotations

from pathlib import Path

from axiom.core.types import ToolResult
from axiom.permissions.sandbox import validate_workspace_path
from axiom.tools.registry import ToolContext

DEFAULT_IGNORE = {".git", "__pycache__", ".axiom", "node_modules", ".venv", "venv", ".pytest_cache"}


def _resolve_path(raw_path: str, workspace: str) -> Path:
    """Resolve a relative/absolute path within the workspace (public helper).

    Raises WorkspaceBoundaryError for escapes.
    """
    return validate_workspace_path(raw_path, workspace)


def _err(name: str, message: str) -> ToolResult:
    return ToolResult(tool_call_id="", name=name, content=f"Error: {message}", is_error=True)


def _ok(name: str, content: str) -> ToolResult:
    return ToolResult(tool_call_id="", name=name, content=content)


async def read_file(
    path: str, offset: int = 1, limit: int | None = None, _context: ToolContext | None = None
) -> ToolResult:
    """Read a text file inside the workspace. offset is a 1-based line number."""
    ctx = _context
    try:
        p = _resolve_path(path, ctx.workspace)
    except Exception as exc:
        return _err("read_file", f"path outside workspace or invalid: {exc}")
    if not p.is_file():
        return _err("read_file", f"file not found: {path}")
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return _err("read_file", f"cannot read {path}: {exc}")
    start = max(0, offset - 1)
    selected = lines[start:] if limit is None else lines[start : start + limit]
    body = "\n".join(selected)
    return _ok("read_file", body or "(empty)")


async def write_file(path: str, content: str, _context: ToolContext) -> ToolResult:
    try:
        p = _resolve_path(path, _context.workspace)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except Exception as exc:
        return _err("write_file", str(exc))
    return _ok("write_file", f"Wrote {len(content)} chars to {path}")


async def edit_file(
    path: str, old_text: str, new_text: str, replace_all: bool = False,
    _context: ToolContext = None,  # type: ignore[assignment]
) -> ToolResult:
    """Replace old_text with new_text in a file (exact match, non-destructive)."""
    try:
        p = _resolve_path(path, _context.workspace)
        if not p.is_file():
            return _err("edit_file", f"file not found: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return _err("edit_file", str(exc))
    if old_text not in text:
        return _err("edit_file", f"old text not found in {path}")
    count = text.count(old_text)
    text = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
    try:
        p.write_text(text, encoding="utf-8")
    except OSError as exc:
        return _err("edit_file", f"cannot write {path}: {exc}")
    replaced = f"{count} occurrence(s)" if replace_all else "1 occurrence"
    return _ok("edit_file", f"Edited {path}: replaced {replaced}.")


async def delete_file(path: str, _context: ToolContext) -> ToolResult:
    try:
        p = _resolve_path(path, _context.workspace)
        if not p.exists():
            return _err("delete_file", f"file not found: {path}")
        if p.is_dir():
            import shutil

            shutil.rmtree(p)
            return _ok("delete_file", f"Deleted directory {path}")
        p.unlink()
    except Exception as exc:
        return _err("delete_file", str(exc))
    return _ok("delete_file", f"Deleted {path}")


async def list_directory(path: str = ".", _context: ToolContext = None) -> ToolResult:  # type: ignore[assignment]
    try:
        p = _resolve_path(path, _context.workspace)
        if not p.is_dir():
            return _err("list_directory", f"directory not found: {path}")
    except Exception as exc:
        return _err("list_directory", str(exc))
    ignore = set((_context.config or {}).get("ignore_patterns", []) or DEFAULT_IGNORE)
    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except OSError as exc:
        return _err("list_directory", f"cannot list {path}: {exc}")
    visible = [e for e in entries if e.name not in ignore and not e.name.startswith(".")]
    if not visible:
        return _ok("list_directory", "(empty directory)")
    lines = []
    for entry in visible:
        if entry.is_dir():
            lines.append(f"[DIR]  {entry.name}")
        else:
            lines.append(f"       {entry.name}  {entry.stat().st_size}b")
    return _ok("list_directory", "\n".join(lines))


async def search_files(
    query: str, path: str = ".", glob: str = "**/*",
    _context: ToolContext = None,  # type: ignore[assignment]
) -> ToolResult:
    """Search file contents and names for a literal, case-insensitive query."""
    try:
        root = _resolve_path(path, _context.workspace)
        if not root.exists():
            return _err("search_files", f"path not found: {path}")
    except Exception as exc:
        return _err("search_files", str(exc))
    ignore = set((_context.config or {}).get("ignore_patterns", []) or DEFAULT_IGNORE)
    lowered = query.lower()
    matches: list[str] = []
    limit = 80
    for f in root.glob(glob):
        if not f.is_file():
            continue
        if set(f.parts) & ignore:
            continue
        name_hit = lowered in f.name.lower()
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if name_hit or lowered in text.lower():
            matches.append(str(f.relative_to(root)))
            if len(matches) >= limit:
                break
    if not matches:
        return _ok("search_files", f"No matches for '{query}'")
    return _ok("search_files", "\n".join(matches))
