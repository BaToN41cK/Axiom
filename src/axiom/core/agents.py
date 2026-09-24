"""AgentRegistry: реестр агентов без правок Core."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentProfile:
    id: str
    label: str = ""
    provider_id: str = "ollama"
    model: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    temperature: float | None = None

    def name(self) -> str:
        return self.label or self.id

DEFAULT_AGENTS: tuple[AgentProfile, ...] = (
    AgentProfile("orchestrator", "Orchestrator"),
    AgentProfile("analyst", "Analyst"),
    AgentProfile("coder", "Coder"),
    AgentProfile("debugger", "Debugger"),
    AgentProfile("reviewer", "Reviewer"),
    AgentProfile("researcher", "Researcher"),
    AgentProfile("tester", "Tester"),
    AgentProfile("architect", "Architect"),
    AgentProfile("security", "Security"),
)

class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentProfile] = {a.id: a for a in DEFAULT_AGENTS}

    def register(self, profile: AgentProfile) -> None:
        self._agents[profile.id] = profile

    def remove(self, agent_id: str) -> bool:
        return self._agents.pop(agent_id, None) is not None

    def get(self, agent_id: str) -> AgentProfile | None:
        return self._agents.get(agent_id)

    def all(self) -> list[AgentProfile]:
        return list(self._agents.values())

    def ids(self) -> list[str]:
        return list(self._agents)
