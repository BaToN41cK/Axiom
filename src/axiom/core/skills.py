"""Skills — инструкции+tools+знания по стеку (п.14).

Skill: instructions, tools, knowledge, commands, validation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Skill:
    id: str
    label: str = ""
    instructions: str = ""
    tools: tuple[str, ...] = ()
    knowledge: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    validation: tuple[str, ...] = ()

    def prompt_block(self) -> str:
        lines = [f"Skill: {self.label or self.id}", self.instructions.strip()]
        if self.commands:
            lines.append("Commands: " + ", ".join(self.commands))
        if self.validation:
            lines.append("Validate: " + ", ".join(self.validation))
        return "\n".join(line for line in lines if line)


BUILTIN_SKILLS: tuple[Skill, ...] = (
    Skill("python", "Python", "Пиши типобезопасный Python 3.11+, pytest для тестов.",
          ("read_file", "write_file", "edit_file", "run_command", "search_text"),
          ("stdlib", "pytest", "ruff"), ("pytest -q", "ruff check ."), ("pytest -q",)),
    Skill("react", "React", "Функциональные компоненты, hooks, TypeScript.",
          ("read_file", "write_file", "edit_file", "search_text"),
          ("hooks", "vite"), ("npm test", "npm run build"), ("npm test",)),
    Skill("typescript", "TypeScript", "Строгая типизация, без any без нужды.",
          ("read_file", "write_file", "edit_file", "search_text"),
          ("tsc",), ("npx tsc --noEmit",), ("npx tsc --noEmit",)),
    Skill("rust", "Rust", "clippy-clean код, cargo test обязателен.",
          ("read_file", "write_file", "edit_file", "run_command"),
          ("cargo",), ("cargo test", "cargo clippy"), ("cargo test",)),
    Skill("tauri", "Tauri", "npm+cargo мост, IPC команды, frontend/backend граница.",
          ("read_file", "search_text", "run_command"),
          ("ipc", "cargo-tauri"), ("npm run tauri dev",), ("cargo check",)),
    Skill("git", "Git", "Атомарные коммиты, ветки по фичам, review diff перед push.",
          ("git_status", "git_diff", "git_log", "git_branch"), ("rebase",), (), ()),
    Skill("docker", "Docker", "Многослойные образы, .dockerignore, healthcheck.",
          ("read_file", "write_file", "run_command"), ("compose",),
          ("docker build .",), ("docker compose config",)),
    Skill("testing", "Testing", "Покрывай краевые случаи, сначала красный тест.",
          ("read_file", "run_command", "search_text"), ("pytest", "vitest"), ("pytest -q",), ()),
    Skill("debugging", "Debugging", "Воспроизведи, сузь, исправь, проверь регрессию.",
          ("read_file", "search_text", "run_command", "git_diff"),
          ("bisect",), (), ("pytest -q",)),
    Skill("security", "Security", "Не коммить секреты, проверяй ввод,最小 привилегии.",
          ("read_file", "search_text", "git_diff"), ("owasp",), (), ()),
    Skill("sql", "SQL", "Параметризованные запросы, explain перед оптимизацией.",
          ("read_file", "search_text"), ("postgres",), (), ()),
)

_MATCH: dict[str, tuple[str, ...]] = {
    "python": ("python", ".py", "pytest", "pip", "питон"),
    "react": ("react", ".tsx", ".jsx", "vite", "реакт"),
    "typescript": ("typescript", ".ts", "tsc", "тайпскрипт"),
    "rust": ("rust", ".rs", "cargo", "раст"),
    "tauri": ("tauri", "ipc"),
    "git": ("git", "коммит", "commit", "branch", "ветк"),
    "docker": ("docker", "compose", "докер"),
    "testing": ("test", "тест", "pytest", "vitest"),
    "debugging": ("debug", "баг", "bug", "ошибк", "падает", "исправ"),
    "security": ("secur", "безопас", "cve", "auth", "аутентиф"),
    "sql": ("sql", "postgres", "select", "запрос"),
}


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {s.id: s for s in BUILTIN_SKILLS}
        self._pin_sources: dict[str, set[str]] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.id] = skill

    def remove(self, skill_id: str) -> bool:
        removed = self._skills.pop(skill_id, None) is not None
        self._pin_sources.pop(skill_id, None)
        return removed

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def resolve_for_task(self, text: str) -> list[Skill]:
        lowered = (text or "").lower()
        out: list[Skill] = []
        for skill_id, markers in _MATCH.items():
            if any(m in lowered for m in markers):
                skill = self._skills.get(skill_id)
                if skill is not None and skill not in out:
                    out.append(skill)
        # Pinned skills (плагины/пресеты) доступны всегда — независимо от маркеров.
        for skill_id in self._pin_sources:
            skill = self._skills.get(skill_id)
            if skill is not None and skill not in out:
                out.append(skill)
        return out

    def pin(self, skill_id: str, *, source: str = "manual") -> bool:
        """Закрепить skill для источника; он попадает в контекст всегда."""
        if skill_id not in self._skills:
            return False
        self._pin_sources.setdefault(skill_id, set()).add(source)
        return True

    def unpin(self, skill_id: str, *, source: str | None = None) -> bool:
        """Снять pin одного источника или все pins при ``source=None``."""
        sources = self._pin_sources.get(skill_id)
        if not sources:
            return False
        if source is None:
            self._pin_sources.pop(skill_id, None)
            return True
        if source not in sources:
            return False
        sources.discard(source)
        if not sources:
            self._pin_sources.pop(skill_id, None)
        return True

    def pinned(self) -> list[str]:
        return sorted(self._pin_sources)
