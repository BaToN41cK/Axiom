"""Agent Presets + runtime profiles/режимы (п.22, п.33-34).

Preset: Model + Tools + Skills + Permissions + Temperature + Reasoning +
Context + Budget + Fallback. Режимы — runtime profiles поверх пресетов:
chat / code / agent / research / review / debug (+ code-agent PTC).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentPreset:
    """Preset schema; runtime applies supported fields and reports the rest.

    ``provider_id``, ``model``, ``tools`` and ``fallbacks`` are descriptive
    only: this session has no preset-specific provider/model switch or tool
    allowlist API. ``reasoning`` and ``context_tokens`` map to Config fields.
    """
    name: str
    provider_id: str = "ollama"
    model: str = ""
    tools: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    permission: str = "auto_approve_safe"
    temperature: float | None = None
    reasoning: str | None = None
    context_tokens: int | None = None
    budget: str = "balanced"
    fallbacks: tuple[str, ...] = ()
    code_mode: bool = False


MODES: dict[str, dict] = {
    "chat": {"agents": ["researcher"], "code_mode": False,
             "hint": "Обычный диалог, быстрый ответ."},
    "code": {"agents": ["architect", "coder", "tester", "reviewer"], "code_mode": False,
             "hint": "Написание и правка кода с верификацией."},
    "agent": {"agents": ["orchestrator", "coder", "debugger", "tester", "reviewer"],
              "code_mode": False, "hint": "Полный harness-цикл через Orchestrator."},
    "research": {"agents": ["researcher", "architect"], "code_mode": False,
                 "hint": "Анализ и поиск, минимум записи."},
    "review": {"agents": ["reviewer", "security"], "code_mode": False,
               "hint": "Ревью diff, без правок."},
    "debug": {"agents": ["debugger", "coder", "tester"], "code_mode": False,
              "hint": "Воспроизведение и исправление бага."},
    "code-agent": {"agents": ["coder"], "code_mode": True,
                   "hint": "Code/PTC: модель пишет мини-программу оркестрации тулов."},
}


def detect_mode(text: str) -> str:
    lowered = (text or "").lower()
    if any(k in lowered for k in ("что делает", "найди", "исследуй", "research", "изучи")):
        return "research"
    if any(k in lowered for k in ("исправ", "падает", "баг", "bug", "debug", "ошибк")):
        return "debug"
    if any(k in lowered for k in ("проверь", "review", "ревью", "pr ")):
        return "review"
    if any(k in lowered for k in ("реализуй", "напиши код", "implement", "рефактор", "добавь")):
        return "code"
    if any(k in lowered for k in ("запланируй", "агент", "оркестр", "сделай всё", "harness")):
        return "agent"
    return "chat"


class PresetStore:
    def __init__(self) -> None:
        self._presets: dict[str, AgentPreset] = {
            "coding": AgentPreset("coding", model="", tools=("read_file", "write_file",
                                  "edit_file", "run_command"), skills=("python", "testing"),
                                  budget="balanced"),
            "review": AgentPreset("review", tools=("read_file", "git_diff"),
                                  skills=("security",), budget="economy"),
        }

    def save_preset(self, preset: AgentPreset) -> None:
        self._presets[preset.name] = preset

    def get(self, name: str) -> AgentPreset | None:
        return self._presets.get(name)

    def remove(self, name: str) -> bool:
        return self._presets.pop(name, None) is not None

    def list(self) -> list[AgentPreset]:
        return list(self._presets.values())
