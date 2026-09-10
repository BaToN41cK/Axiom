"""Project intelligence: detect language, framework, tests, git, structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectInfo:
    """Compact project description sent to the model as context."""

    language: str = "unknown"
    language_version: str = ""
    framework: str = ""
    package_manager: str = ""
    test_framework: str = ""
    build_system: str = ""
    has_git: bool = False
    entry_points: list[str] = field(default_factory=list)
    important_dirs: list[str] = field(default_factory=list)
    file_count: int = 0

    def summary(self) -> str:
        lines = [
            f"Language: {self.language}{' ' + self.language_version if self.language_version else ''}",
        ]
        if self.framework:
            lines.append(f"Framework: {self.framework}")
        if self.package_manager:
            lines.append(f"Package manager: {self.package_manager}")
        if self.test_framework:
            lines.append(f"Tests: {self.test_framework}")
        if self.build_system:
            lines.append(f"Build: {self.build_system}")
        lines.append(f"Git: {'yes' if self.has_git else 'no'}")
        if self.entry_points:
            lines.append(f"Entry points: {', '.join(self.entry_points)}")
        if self.important_dirs:
            lines.append(f"Directories: {', '.join(self.important_dirs)}")
        lines.append(f"Files: ~{self.file_count}")
        return "\n".join(lines)


def _count_files(root: Path, ignore: set[str], limit: int = 5000) -> int:
    count = 0
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        if ignore & set(f.parts):
            continue
        count += 1
        if count >= limit:
            break
    return count


def detect_project(root: Path) -> ProjectInfo:
    """Detect project properties from marker files."""
    info = ProjectInfo()
    ignore = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache", ".axiom"}
    info.has_git = (root / ".git").exists()

    if (root / "pyproject.toml").is_file():
        text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
        info.language = "Python"
        info.package_manager = "uv" if (root / "uv.lock").is_file() else (
            "poetry" if "[tool.poetry]" in text else "pip"
        )
        if "pytest" in text:
            info.test_framework = "pytest"
        if "textual" in text or "rich" in text:
            info.framework = info.framework or "TUI"
        if "hatchling" in text or "setuptools" in text:
            info.build_system = "pyproject (PEP 517)"
        if "[project.scripts]" in text:
            for line in text.splitlines():
                if line.strip().startswith("axiom") or "=" in line and "[project.scripts]" not in line:
                    pass
    elif (root / "setup.py").is_file():
        info.language = "Python"
        info.package_manager = "pip"
    elif (root / "requirements.txt").is_file():
        info.language = "Python"
        info.package_manager = "pip"
        reqs = (root / "requirements.txt").read_text(encoding="utf-8", errors="ignore").lower()
        if "pytest" in reqs:
            info.test_framework = "pytest"

    if info.language == "unknown":
        if (root / "package.json").is_file():
            info.language = "JavaScript/TypeScript"
            try:
                pkg = (root / "package.json").read_text(encoding="utf-8", errors="ignore")
                if "react" in pkg:
                    info.framework = "React"
                if "vue" in pkg:
                    info.framework = "Vue"
                if '"test"' in pkg and "vitest" in pkg:
                    info.test_framework = "vitest"
                elif "jest" in pkg:
                    info.test_framework = "jest"
            except OSError:
                pass
            info.package_manager = "pnpm" if (root / "pnpm-lock.yaml").is_file() else (
                "yarn" if (root / "yarn.lock").is_file() else "npm"
            )
        elif (root / "Cargo.toml").is_file():
            info.language = "Rust"
            info.package_manager = "cargo"
            info.test_framework = "cargo test"
            info.build_system = "cargo"
        elif (root / "go.mod").is_file():
            info.language = "Go"
            info.test_framework = "go test"
        elif (root / "*.csproj").exists() or any(root.glob("*.csproj")):
            info.language = "C#"
            info.package_manager = "dotnet"
            info.test_framework = "dotnet test"

    # Entry points
    for candidate in ("main.py", "app.py", "__main__.py", "index.js", "main.rs", "main.go"):
        if (root / candidate).is_file():
            info.entry_points.append(candidate)

    # Important dirs
    for d in ("src", "tests", "docs", "config", "scripts"):
        if (root / d).is_dir():
            info.important_dirs.append(d)

    # Python version hint
    if (root / ".python-version").is_file():
        info.language_version = (
            (root / ".python-version").read_text(encoding="utf-8").strip().splitlines()[0]
        )

    try:
        info.file_count = _count_files(root, ignore)
    except OSError:
        info.file_count = 0
    return info
