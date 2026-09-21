"""Workspace / project management — real directories, recent projects, detection.

AXIOM is workspace-aware: the agent, terminal and explorer all operate on the
same ``workspace_root``.  This module knows nothing about Ollama or UI — it is
pure project bookkeeping backed by a real JSON file under ``~/.axiom``.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from axiom.core.config import axiom_home

STORE_PATH = axiom_home() / "workspaces.json"
MAX_RECENT = 12

#: Marker file -> project kind. First match wins.
PROJECT_MARKERS: tuple[tuple[str, str], ...] = (
    ("pyproject.toml", "Python"),
    ("requirements.txt", "Python"),
    ("setup.py", "Python"),
    ("setup.cfg", "Python"),
    ("Pipfile", "Python"),
    ("uv.lock", "Python"),
    ("package.json", "Node / JS"),
    ("tsconfig.json", "TypeScript"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("pom.xml", "Java (Maven)"),
    ("build.gradle", "Java (Gradle)"),
    ("build.gradle.kts", "Java (Gradle)"),
    ("*.csproj", "C# / .NET"),
    ("*.sln", "C# / .NET"),
    ("composer.json", "PHP"),
    ("Gemfile", "Ruby"),
    ("CMakeLists.txt", "C/C++"),
    ("Makefile", "C/C++"),
    ("*.xcodeproj", "Swift / ObjC"),
    ("pubspec.yaml", "Dart / Flutter"),
    ("mix.exs", "Elixir"),
    ("tauri.conf.json", "Tauri"),
)


@dataclass
class ProjectInfo:
    """Detected facts about a real directory."""

    path: str
    name: str
    kind: str = "Unknown"
    git: bool = False
    branch: str | None = None
    entries: list[str] = field(default_factory=list)
    pinned: bool = False

    def to_json(self) -> dict:
        d = {
            "path": self.path,
            "name": self.name,
            "kind": self.kind,
            "git": self.git,
            "branch": self.branch,
            "entries": self.entries,
        }
        if self.pinned:
            d["pinned"] = True
        return d


def detect_project(path: Path) -> ProjectInfo:
    """Inspect a real directory: project kind, git branch, top-level layout."""
    path = path.resolve()
    name = path.name or str(path)
    kind = "Unknown"
    for marker, label in PROJECT_MARKERS:
        if marker.startswith("*"):
            if any(path.glob(marker)):
                kind = label
                break
        elif (path / marker).exists():
            kind = label
            break
    git = (path / ".git").exists()
    branch: str | None = None
    if git:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=path,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if out.returncode == 0:
                branch = out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            branch = None
    try:
        entries = sorted(
            e.name + ("/" if e.is_dir() else "") for e in path.iterdir() if not e.name.startswith(".")
        )[:24]
    except OSError:
        entries = []
    return ProjectInfo(path=str(path), name=name, kind=kind, git=git, branch=branch, entries=entries)


def project_slug(path: Path) -> str:
    """Stable per-project directory name: ``<name>-<8 hex of absolute path>``."""
    import hashlib

    resolved = str(path.resolve())
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:8]
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in path.resolve().name)[:40]
    return f"{safe or 'project'}-{digest}"


class WorkspaceManager:
    """Persistent list of recent projects (``~/.axiom/workspaces.json``).

    Each entry is a dict with ``path`` and optional ``pinned`` fields.
    """

    def __init__(self) -> None:
        self._recent: list[dict] = self._load()
        self._pinned: list[str] = self._load_pinned()

    def clear(self) -> None:
        """Clear all in-memory and persistent state (for testing/cleanup)."""
        self._recent.clear()
        self._pinned.clear()
        self._save()

    # ------------------------------------------------------------- storage

    def _load(self) -> list[dict]:
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [
                    {"path": str(p), "pinned": False}
                    if isinstance(p, str)
                    else {"path": str(p.get("path", "")), "pinned": bool(p.get("pinned", False))}
                    for p in data
                ]
        except (OSError, ValueError):
            pass
        return []

    def _load_pinned(self) -> list[str]:
        try:
            path = STORE_PATH.with_suffix(".pinned.json")
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(p) for p in data if Path(p).exists()]
        except (OSError, ValueError):
            pass
        return []

    def _save(self) -> None:
        try:
            STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STORE_PATH.write_text(
                json.dumps(
                    [{"path": p["path"], "pinned": p.get("pinned", False)} for p in self._recent],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            pin_path = STORE_PATH.with_suffix(".pinned.json")
            pin_path.write_text(
                json.dumps(self._pinned, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # -------------------------------------------------------------- queries

    def recent(self) -> list[ProjectInfo]:
        return [detect_project(Path(p["path"])) for p in self._recent if Path(p["path"]).exists()]

    def pinned_projects(self) -> list[ProjectInfo]:
        return [detect_project(Path(p)) for p in self._pinned if Path(p).exists()]

    def remember(self, path: Path) -> None:
        """Move a project to the front of the recents list."""
        key = str(path.resolve())
        for i, p in enumerate(self._recent):
            if p["path"] == key:
                self._recent.pop(i)
                break
        self._recent.insert(0, {"path": key, "pinned": False})
        del self._recent[MAX_RECENT:]
        self._save()

    def remove(self, path: str) -> bool:
        key = str(Path(path).resolve())
        self._recent = [p for p in self._recent if p["path"] != key]
        self._pinned = [p for p in self._pinned if p != key]
        self._save()
        return True

    def pin(self, path: str) -> bool:
        key = str(Path(path).resolve())
        if key in self._pinned:
            return False
        if any(p["path"] == key for p in self._recent):
            for p in self._recent:
                if p["path"] == key:
                    p["pinned"] = True
            self._save()
        self._pinned.append(key)
        self._save()
        return True

    def unpin(self, path: str) -> bool:
        key = str(Path(path).resolve())
        self._pinned = [p for p in self._pinned if p != key]
        for p in self._recent:
            if p["path"] == key:
                p["pinned"] = False
        self._save()
        return True

    def is_pinned(self, path: str) -> bool:
        key = str(Path(path).resolve())
        return key in self._pinned

    def search_projects(self, query: str) -> list[ProjectInfo]:
        """Search recent projects by name or path."""
        q = query.strip().lower()
        if not q:
            return []
        results = []
        for p in self._recent:
            if not Path(p["path"]).exists():
                continue
            info = detect_project(Path(p["path"]))
            if q in info.name.lower() or q in info.path.lower():
                results.append(info)
        return results

    def create_project(self, path: Path) -> ProjectInfo:
        """Create a new project directory and remember it."""
        path = path.expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        self.remember(path)
        return detect_project(path)
