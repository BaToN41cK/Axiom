"""Workspace filesystem tools — AXIOM's hands inside the user's project.

Every path is sandboxed to the workspace root: the model can never read or
write outside it, even with a crafted relative path. Tools mirror what a
coding agent needs: list, read, create/overwrite, and surgical edit.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
from pathlib import Path

from axiom.core.tools.base import ToolDefinition, ToolPermission, ToolResult

LIST_FILES_TOOL = "list_files"
READ_FILE_TOOL = "read_file"
WRITE_FILE_TOOL = "write_file"
EDIT_FILE_TOOL = "edit_file"
SEARCH_TEXT_TOOL = "search_text"
SEARCH_FILES_TOOL = "search_files"
DELETE_FILE_TOOL = "delete_file"
MOVE_FILE_TOOL = "move_file"
COPY_FILE_TOOL = "copy_file"
CREATE_DIR_TOOL = "create_directory"

WORKSPACE_TOOLS = (
    LIST_FILES_TOOL, READ_FILE_TOOL, WRITE_FILE_TOOL, EDIT_FILE_TOOL,
    SEARCH_TEXT_TOOL, SEARCH_FILES_TOOL, DELETE_FILE_TOOL, MOVE_FILE_TOOL,
    COPY_FILE_TOOL, CREATE_DIR_TOOL,
)

#: Safety limits — a model must not be able to stall on huge inputs.
MAX_READ_CHARS = 24_000
MAX_WRITE_CHARS = 200_000
MAX_LIST_ENTRIES = 400
MAX_SEARCH_HITS = 60
IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", "dist",
    "build", ".mypy_cache", ".ruff_cache", ".pytest_cache", "target",
}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".txt", ".toml",
    ".yaml", ".yml", ".css", ".html", ".rs", ".go", ".c", ".h", ".cpp",
    ".sh", ".cfg", ".ini", ".sql", ".svg", ".xml", ".csv", ".env", ".lock",
}


def default_workspace_root() -> Path:
    """Workspace the bridge was launched in (``AXIOM_WORKSPACE`` overrides)."""
    override = os.environ.get("AXIOM_WORKSPACE")
    return Path(override).expanduser() if override else Path.cwd()


class WorkspaceTools:
    """Registers real, sandboxed filesystem tools in a registry."""

    def __init__(self, root: Path | None = None, access_mode: str = "workspace") -> None:
        self.root = (root or default_workspace_root()).resolve()
        self.access_mode = access_mode

    def set_root(self, root: Path) -> None:
        """Switch the sandbox root (project switch)."""
        self.root = root.resolve()

    def _can_write(self) -> bool:
        return self.access_mode != "read_only"

    def _permission(self, write: bool = False) -> ToolPermission:
        """Permission level for a tool based on access mode.

        In read_only mode all write/modify tools are NEVER offered.
        """
        if write and self.access_mode == "read_only":
            return ToolPermission.NEVER
        if self.access_mode == "read_only":
            return ToolPermission.ALWAYS
        return ToolPermission.ASK

    def resolve(self, path: str) -> Path:
        """Resolve ``path`` inside the workspace; reject any escape."""
        raw = (path or "").strip()
        if not raw:
            raise ValueError("Path is empty")
        candidate = Path(raw)
        full = candidate if candidate.is_absolute() else self.root / candidate
        full = full.resolve()
        root = self.root
        if full != root and root not in full.parents:
            raise ValueError(f"Path '{path}' is outside the workspace ({root})")
        return full

    # ------------------------------------------------------------- definitions

    def _list_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=LIST_FILES_TOOL,
            description=(
                "List files and folders in the workspace. "
                "Use a subdirectory path to explore, or '.' for the root."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory inside the workspace ('.' = root).",
                    },
                },
                "required": ["path"],
            },
            permission=self._permission(write=False),
        )

    def _read_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=READ_FILE_TOOL,
            description=(
                "Read a text file from the workspace. Use it to inspect code "
                "before editing or answering questions about the project."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the workspace."},
                },
                "required": ["path"],
            },
            permission=self._permission(write=False),
        )

    def register(self, registry) -> None:
        """Attach all workspace tools to a :class:`ToolRegistry`."""
        for definition, handler in (
            (self._list_definition(), self._list_files),
            (self._read_definition(), self._read_file),
            (self._search_text_definition(), self._search_text),
            (self._search_files_definition(), self._search_files),
            (self._write_definition(), self._write_file),
            (self._edit_definition(), self._edit_file),
            (self._create_dir_definition(), self._create_directory),
            (self._delete_definition(), self._delete_file),
            (self._move_definition(), self._move_file),
            (self._copy_definition(), self._copy_file),
        ):
            registry.register(definition, handler)

    # ------------------------------------------------------------- definitions

    def _search_text_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=SEARCH_TEXT_TOOL,
            description=(
                "Search file contents across the workspace for a text substring. "
                "Returns matching files with line numbers — use it to locate code "
                "relevant to the task."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for (case-insensitive)."},
                    "glob": {"type": "string", "description": "Optional filename filter, e.g. '*.py'."},
                },
                "required": ["query"],
            },
            permission=self._permission(write=False),
        )

    def _search_files_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=SEARCH_FILES_TOOL,
            description="Find files in the workspace by glob pattern (e.g. '*.ts', 'auth*').",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern matched against file names."},
                },
                "required": ["pattern"],
            },
            permission=self._permission(write=False),
        )

    def _create_dir_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=CREATE_DIR_TOOL,
            description="Create a directory (and parents) inside the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path relative to the workspace."},
                },
                "required": ["path"],
            },
            permission=self._permission(write=True),
        )

    def _delete_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=DELETE_FILE_TOOL,
            description=(
                "Delete a file or a directory (recursively) inside the workspace. "
                "Use sparingly — the action is hard to undo."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the workspace."},
                },
                "required": ["path"],
            },
            permission=self._permission(write=True),
        )

    def _move_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=MOVE_FILE_TOOL,
            description="Move or rename a file/directory within the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Existing path."},
                    "destination": {"type": "string", "description": "New path."},
                },
                "required": ["source", "destination"],
            },
            permission=self._permission(write=True),
        )

    def _copy_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=COPY_FILE_TOOL,
            description="Copy a file (or directory, recursively) within the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Existing path."},
                    "destination": {"type": "string", "description": "Target path."},
                },
                "required": ["source", "destination"],
            },
            permission=self._permission(write=True),
        )

    def _write_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=WRITE_FILE_TOOL,
            description=(
                "Create a new file or completely overwrite an existing one "
                "with the given content inside the workspace."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the workspace."},
                    "content": {"type": "string", "description": "Full new file content."},
                },
                "required": ["path", "content"],
            },
            permission=self._permission(write=True),
        )

    def _edit_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=EDIT_FILE_TOOL,
            description=(
                "Replace an exact snippet inside an existing workspace file. "
                "old_text must match the file verbatim and be unique; use it "
                "for surgical edits instead of rewriting the whole file."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to the workspace."},
                    "old_text": {"type": "string", "description": "Exact existing text to replace."},
                    "new_text": {"type": "string", "description": "Replacement text."},
                },
                "required": ["path", "old_text", "new_text"],
            },
            permission=self._permission(write=True),
        )

    # ------------------------------------------------------------- handlers

    async def _list_files(self, path: str = ".") -> ToolResult:
        directory = self.resolve(path)
        if not directory.exists():
            return ToolResult(name=LIST_FILES_TOOL, ok=False, error=f"No such directory: {path}")
        if not directory.is_dir():
            return ToolResult(name=LIST_FILES_TOOL, ok=False, error=f"Not a directory: {path}")
        lines: list[str] = []
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError as exc:
            return ToolResult(name=LIST_FILES_TOOL, ok=False, error=f"Cannot list: {exc}")
        for entry in entries:
            if len(lines) >= MAX_LIST_ENTRIES:
                lines.append(f"… truncated ({MAX_LIST_ENTRIES} entries max)")
                break
            if entry.name.startswith(".") and entry.name != ".vscode":
                continue
            if entry.is_dir() and entry.name in IGNORED_DIRS:
                continue
            if entry.is_dir():
                lines.append(f"{entry.name}/")
            else:
                size = entry.stat().st_size if entry.exists() else 0
                lines.append(f"{entry.name} ({size} B)")
        body = "\n".join(lines) if lines else "(empty directory)"
        rel = directory.relative_to(self.root) if directory != self.root else Path(".")
        return ToolResult(name=LIST_FILES_TOOL, ok=True, content=body, data={"path": str(rel)})

    async def _read_file(self, path: str) -> ToolResult:
        target = self.resolve(path)
        if not target.exists():
            return ToolResult(name=READ_FILE_TOOL, ok=False, error=f"No such file: {path}")
        if target.is_dir():
            return ToolResult(name=READ_FILE_TOOL, ok=False, error=f"'{path}' is a directory — use list_files")
        if target.suffix.lower() not in TEXT_SUFFIXES and target.stat().st_size > 2_000_000:
            return ToolResult(name=READ_FILE_TOOL, ok=False, error=f"'{path}' looks binary or too large")
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(name=READ_FILE_TOOL, ok=False, error=f"Cannot read: {exc}")
        truncated = ""
        if len(text) > MAX_READ_CHARS:
            text = text[:MAX_READ_CHARS]
            truncated = f"\n\n… truncated at {MAX_READ_CHARS} characters"
        lines_total = text.count("\n") + 1
        header = f"# {target.relative_to(self.root)} ({lines_total} lines)"
        return ToolResult(name=READ_FILE_TOOL, ok=True, content=header + "\n" + text + truncated)

    async def _write_file(self, path: str, content: str) -> ToolResult:
        if len(content) > MAX_WRITE_CHARS:
            return ToolResult(name=WRITE_FILE_TOOL, ok=False, error="Content exceeds size limit")
        target = self.resolve(path)
        existed = target.exists()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(name=WRITE_FILE_TOOL, ok=False, error=f"Cannot write: {exc}")
        verb = "Overwrote" if existed else "Created"
        lines = content.count("\n") + 1
        return ToolResult(
            name=WRITE_FILE_TOOL,
            ok=True,
            content=f"{verb} {target.relative_to(self.root)} ({lines} lines, {len(content)} chars)",
        )

    async def _edit_file(self, path: str, old_text: str, new_text: str) -> ToolResult:
        target = self.resolve(path)
        if not target.exists() or target.is_dir():
            return ToolResult(name=EDIT_FILE_TOOL, ok=False, error=f"No such file: {path}")
        try:
            text = target.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(name=EDIT_FILE_TOOL, ok=False, error=f"Cannot read: {exc}")
        matches = text.count(old_text) if old_text else 0
        if matches == 0:
            return ToolResult(
                name=EDIT_FILE_TOOL,
                ok=False,
                error="old_text not found in file — read the file first and copy the snippet exactly",
            )
        if matches > 1:
            return ToolResult(
                name=EDIT_FILE_TOOL,
                ok=False,
                error=f"old_text matches {matches} places — provide a larger unique snippet",
            )
        updated = text.replace(old_text, new_text, 1)
        try:
            target.write_text(updated, encoding="utf-8")
        except OSError as exc:
            return ToolResult(name=EDIT_FILE_TOOL, ok=False, error=f"Cannot write: {exc}")
        return ToolResult(
            name=EDIT_FILE_TOOL,
            ok=True,
            content=f"Edited {target.relative_to(self.root)}: replaced {len(old_text)} chars with {len(new_text)}",
        )

    def _iter_text_files(self, directory: Path):
        """Yield text files under ``directory`` skipping ignored/hidden dirs."""
        if not directory.is_dir():
            return
        try:
            for root, dirs, files in os.walk(directory):
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
                for name in files:
                    path = Path(root) / name
                    if path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size <= 1_000_000:
                        yield path
        except OSError:
            return

    async def _search_text(self, query: str, glob: str | None = None) -> ToolResult:
        if not query.strip():
            return ToolResult(name=SEARCH_TEXT_TOOL, ok=False, error="Query is empty")
        needle = query.lower()
        hits: list[str] = []
        for path in self._iter_text_files(self.root):
            if glob and not fnmatch.fnmatch(path.name, glob):
                continue
            try:
                for lineno, line in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
                ):
                    if needle in line.lower():
                        rel = path.relative_to(self.root)
                        hits.append(f"{rel}:{lineno}: {line.strip()[:160]}")
                        if len(hits) >= MAX_SEARCH_HITS:
                            break
            except OSError:
                continue
            if len(hits) >= MAX_SEARCH_HITS:
                break
        if not hits:
            return ToolResult(name=SEARCH_TEXT_TOOL, ok=True, content=f"No matches for '{query}'")
        body = "\n".join(hits)
        if len(hits) >= MAX_SEARCH_HITS:
            body += f"\n… truncated ({MAX_SEARCH_HITS} matches max)"
        return ToolResult(name=SEARCH_TEXT_TOOL, ok=True, content=body)

    async def _search_files(self, pattern: str) -> ToolResult:
        if not pattern.strip():
            return ToolResult(name=SEARCH_FILES_TOOL, ok=False, error="Pattern is empty")
        matches: list[str] = []
        try:
            for root, dirs, files in os.walk(self.root):
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
                for name in files:
                    if fnmatch.fnmatch(name, pattern):
                        matches.append(str(Path(root, name).relative_to(self.root)))
                        if len(matches) >= MAX_SEARCH_HITS:
                            break
                if len(matches) >= MAX_SEARCH_HITS:
                    break
        except OSError as exc:
            return ToolResult(name=SEARCH_FILES_TOOL, ok=False, error=f"Cannot search: {exc}")
        if not matches:
            return ToolResult(name=SEARCH_FILES_TOOL, ok=True, content=f"No files match '{pattern}'")
        body = "\n".join(matches)
        if len(matches) >= MAX_SEARCH_HITS:
            body += f"\n… truncated ({MAX_SEARCH_HITS} max)"
        return ToolResult(name=SEARCH_FILES_TOOL, ok=True, content=body)

    async def _create_directory(self, path: str) -> ToolResult:
        if not self._can_write():
            return ToolResult(name=CREATE_DIR_TOOL, ok=False, error="Access is read-only")
        target = self.resolve(path)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return ToolResult(name=CREATE_DIR_TOOL, ok=False, error=f"Cannot create: {exc}")
        return ToolResult(name=CREATE_DIR_TOOL, ok=True, content=f"Created {target.relative_to(self.root)}/")

    async def _delete_file(self, path: str) -> ToolResult:
        if not self._can_write():
            return ToolResult(name=DELETE_FILE_TOOL, ok=False, error="Access is read-only")
        target = self.resolve(path)
        if not target.exists():
            return ToolResult(name=DELETE_FILE_TOOL, ok=False, error=f"No such file: {path}")
        if target == self.root:
            return ToolResult(name=DELETE_FILE_TOOL, ok=False, error="Refusing to delete the workspace root")
        try:
            if target.is_dir():
                shutil.rmtree(target)
                summary = "directory"
            else:
                target.unlink()
                summary = "file"
        except OSError as exc:
            return ToolResult(name=DELETE_FILE_TOOL, ok=False, error=f"Cannot delete: {exc}")
        return ToolResult(
            name=DELETE_FILE_TOOL,
            ok=True,
            content=f"Deleted {summary} {target.relative_to(self.root)}",
        )

    async def _move_file(self, source: str, destination: str) -> ToolResult:
        if not self._can_write():
            return ToolResult(name=MOVE_FILE_TOOL, ok=False, error="Access is read-only")
        src = self.resolve(source)
        dst = self.resolve(destination)
        if not src.exists():
            return ToolResult(name=MOVE_FILE_TOOL, ok=False, error=f"No such file: {source}")
        if dst.exists():
            return ToolResult(name=MOVE_FILE_TOOL, ok=False, error=f"Destination exists: {destination}")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except (OSError, shutil.Error) as exc:
            return ToolResult(name=MOVE_FILE_TOOL, ok=False, error=f"Cannot move: {exc}")
        return ToolResult(
            name=MOVE_FILE_TOOL,
            ok=True,
            content=f"Moved {src.relative_to(self.root)} → {dst.relative_to(self.root)}",
        )

    async def _copy_file(self, source: str, destination: str) -> ToolResult:
        if not self._can_write():
            return ToolResult(name=COPY_FILE_TOOL, ok=False, error="Access is read-only")
        src = self.resolve(source)
        dst = self.resolve(destination)
        if not src.exists():
            return ToolResult(name=COPY_FILE_TOOL, ok=False, error=f"No such file: {source}")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        except (OSError, shutil.Error) as exc:
            return ToolResult(name=COPY_FILE_TOOL, ok=False, error=f"Cannot copy: {exc}")
        return ToolResult(
            name=COPY_FILE_TOOL,
            ok=True,
            content=f"Copied {src.relative_to(self.root)} → {dst.relative_to(self.root)}",
        )

