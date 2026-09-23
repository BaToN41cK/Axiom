"""Project Intelligence + .axiom/ персист (п.19).

Индекс: languages, frameworks, deps, entry points, important files,
git status, build system, tests, architecture. Персист проекта:
.axiom/project.json + index/context/agents/sessions/skills/trajectories.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

ENTRY_CANDIDATES = ("main.py", "app.py", "src/main.py", "desktop/src/App.tsx",
                    "src/index.ts", "src/main.ts", "src/main.rs", "cmd/main.go",
                    "package.json", "pyproject.toml", "Cargo.toml", "go.mod")

LANGUAGE_SUFFIXES: dict[str, str] = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".rs": "Rust", ".go": "Go", ".java": "Java", ".cs": "C#",
    ".php": "PHP", ".rb": "Ruby", ".sql": "SQL", ".sh": "Shell",
}

FRAMEWORK_MARKERS: dict[str, str] = {
    "react": "React", "tauri": "Tauri", "vite": "Vite", "next": "Next.js",
    "django": "Django", "fastapi": "FastAPI", "flask": "Flask",
    "pytest": "pytest", "sqlalchemy": "SQLAlchemy", "pydantic": "pydantic",
}


@dataclass
class ProjectIndex:
    path: str = ""
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    important_files: list[str] = field(default_factory=list)
    git_status: str = ""
    build_system: str = ""
    tests: list[str] = field(default_factory=list)
    architecture: str = ""

    def to_json(self) -> dict:
        return asdict(self)


def index_project(root: Path | str) -> ProjectIndex:
    base = Path(root).resolve()
    index = ProjectIndex(path=str(base))
    try:
        files = [p for p in base.rglob("*") if p.is_file()
                 and ".git" not in p.parts and "node_modules" not in p.parts
                 and ".venv" not in p.parts][:4000]
    except Exception:
        files = []
    langs: dict[str, int] = {}
    for path in files:
        lang = LANGUAGE_SUFFIXES.get(path.suffix.lower())
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    index.languages = sorted(langs, key=lambda k: -langs[k])[:8]
    blob_names = " ".join(p.name.lower() for p in files[:500])
    try:
        blob_text = blob_names + " " + (base / "package.json").read_text(
            encoding="utf-8", errors="replace")[:4000].lower()
    except Exception:
        blob_text = blob_names
    try:
        blob_text += " " + (base / "pyproject.toml").read_text(
            encoding="utf-8", errors="replace")[:4000].lower()
    except Exception:
        pass
    index.frameworks = [label for key, label in FRAMEWORK_MARKERS.items() if key in blob_text][:10]
    for manifest, key in (("package.json", "node"), ("pyproject.toml", "python"),
                          ("Cargo.toml", "rust"), ("go.mod", "go")):
        candidate = base / manifest
        if candidate.exists():
            index.build_system = manifest
            try:
                text = candidate.read_text(encoding="utf-8")
                index.dependencies.append(f"{manifest}: {len(text.splitlines())} lines")
            except Exception:
                pass
            if key == "node" and not index.build_system:
                index.build_system = manifest
    index.entry_points = [c for c in ENTRY_CANDIDATES if (base / c).exists()][:6]
    index.tests = [str(p.relative_to(base)) for p in files
                   if "test" in p.name.lower()][:20]
    important = [c for c in ("README.md", "pyproject.toml", "package.json",
                             "Cargo.toml", "desktop/src/App.tsx", "src/axiom/core/agent.py")
                 if (base / c).exists()]
    index.important_files = important[:12]
    try:
        proc = subprocess.run(["git", "status", "--short", "--branch"], cwd=base,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=8, check=False)
        index.git_status = (proc.stdout or "").strip()[:2000]
    except Exception:
        index.git_status = ""
    arch = [e.name for e in [base / "src", base / "desktop", base / "tests"] if e.exists()]
    index.architecture = ", ".join(arch)
    return index


class ProjectMemory:
    """Персист .axiom/ внутри проекта: project.json + подпапки."""

    SUBDIRS = ("index", "context", "agents", "sessions", "skills", "trajectories")

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.dir = self.root / ".axiom"

    def ensure(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        for sub in self.SUBDIRS:
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        return self.dir

    def save_index(self, index: ProjectIndex) -> Path:
        self.ensure()
        target = self.dir / "index" / "project.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(index.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        top = self.dir / "project.json"
        top.write_text(json.dumps(index.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def load_index(self) -> ProjectIndex | None:
        for candidate in (self.dir / "project.json", self.dir / "index" / "project.json"):
            if candidate.exists():
                try:
                    return ProjectIndex(**json.loads(candidate.read_text(encoding="utf-8")))
                except Exception:
                    continue
        return None
