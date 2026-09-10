"""Skills system: markdown instruction packs selected per project/task."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from axiom.core.logging import get_logger

logger = get_logger("skills")


@dataclass
class Skill:
    name: str
    instructions: str
    keywords: tuple[str, ...] = ()
    tools: list[str] = field(default_factory=list)


BUILTIN_SKILLS: dict[str, Skill] = {
    "python": Skill(
        name="python",
        instructions=(
            "Python: prefer venv; run tests with pytest; use type hints; "
            "follow PEP 8; never commit .venv or __pycache__."
        ),
        keywords=("python", "pytest", ".py"),
    ),
    "rust": Skill(
        name="rust",
        instructions=(
            "Rust: build with cargo; run cargo clippy and cargo fmt; "
            "tests with cargo test; beware of borrow-checker constraints."
        ),
        keywords=("rust", "cargo", ".rs"),
    ),
    "git": Skill(
        name="git",
        instructions=(
            "Git: inspect status/diff before committing; write conventional "
            "commit messages; never commit .env or secrets."
        ),
        keywords=("git", "commit", "branch"),
    ),
    "testing": Skill(
        name="testing",
        instructions=(
            "Testing: run the narrowest relevant tests first, then the full "
            "suite; analyze failures before editing."
        ),
        keywords=("test", "pytest", "spec"),
    ),
    "security": Skill(
        name="security",
        instructions=(
            "Security: validate inputs, escape shell args, no secrets in code, "
            "watch for path traversal and unsafe deserialization."
        ),
        keywords=("security", "vulnerab", "auth"),
    ),
    "web": Skill(
        name="web",
        instructions=(
            "Web: use official docs; verify API shapes from fetched sources; "
            "rate-limit requests."
        ),
        keywords=("http", "api", "web"),
    ),
}


class SkillManager:
    """Loads builtin + project skills (project/.axiom/skills/*.md)."""

    def __init__(self, workspace: Path | None = None) -> None:
        self._skills: dict[str, Skill] = dict(BUILTIN_SKILLS)
        self._load_project_skills(workspace or Path.cwd())

    def _load_project_skills(self, workspace: Path) -> None:
        skills_dir = workspace / ".axiom" / "skills"
        if not skills_dir.is_dir():
            return
        for path in skills_dir.glob("*.md"):
            try:
                self._skills[path.stem] = Skill(
                    name=path.stem, instructions=path.read_text(encoding="utf-8")
                )
            except OSError as exc:
                logger.warning("Failed to load skill %s: %s", path, exc)

    def list_skills(self) -> list[str]:
        return sorted(self._skills)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def select_for(self, task: str, project_info=None) -> list[Skill]:
        """Pick skills relevant to the task/project."""
        text = task.lower()
        selected: list[Skill] = []
        if project_info is not None:
            if project_info.language == "Python":
                selected.append(self._skills["python"])
            if project_info.language == "Rust":
                selected.append(self._skills["rust"])
            if project_info.test_framework:
                selected.append(self._skills["testing"])
            if project_info.has_git:
                selected.append(self._skills["git"])
        for skill in self._skills.values():
            if any(k in text for k in skill.keywords) and skill not in selected:
                selected.append(skill)
        return selected

    def render_block(self, skills: list[Skill]) -> str:
        if not skills:
            return ""
        lines = ["Relevant skills:"]
        for skill in skills:
            lines.append(f"- {skill.name}: {skill.instructions}")
        return "\n".join(lines)
