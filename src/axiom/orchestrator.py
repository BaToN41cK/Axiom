"""Multi-agent orchestrator: plan decomposition, sub-agent lifecycle, synthesis.

Constraints: max_agents, max_depth, timeout, max_iterations per sub-agent.
Permission inheritance from the parent session.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from axiom.agent_roles import ROLES, get_role
from axiom.core.logging import get_logger
from axiom.permissions.manager import PermissionManager

logger = get_logger("orchestrator")

TaskRunner = Callable[["SubTask"], Awaitable[str]]


@dataclass
class SubTask:
    """A unit of work assigned to a sub-agent."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    role: str = "coder"
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | running | done | failed
    result: str = ""


@dataclass
class AgentInstance:
    """A running sub-agent."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    role: str = "coder"
    task: SubTask | None = None
    status: str = "created"
    depth: int = 0
    max_iterations: int = 30
    started_at: float = 0.0
    finished_at: float = 0.0
    output: str = ""
    permission_manager: PermissionManager | None = None
    model_id: str = ""


class Orchestrator:
    """Coordinates sub-agents for a complex task."""

    def __init__(
        self,
        task_runner: TaskRunner | None = None,
        max_agents: int = 4,
        max_depth: int = 2,
        agent_timeout: float = 600.0,
        parent_permissions: PermissionManager | None = None,
    ) -> None:
        self._runner = task_runner
        self._max_agents = max_agents
        self._max_depth = max_depth
        self._agent_timeout = agent_timeout
        self._parent_permissions = parent_permissions
        self._agents: list[AgentInstance] = []
        self._plan: list[SubTask] = []

    # -- properties --------------------------------------------------------
    @property
    def agents(self) -> list[AgentInstance]:
        return list(self._agents)

    @property
    def plan(self) -> list[SubTask]:
        return list(self._plan)

    # -- planning ------------------------------------------------------------
    def create_plan(self, task: str, num_agents: int | None = None) -> list[SubTask]:
        """Decompose a task into role-specialized subtasks."""
        lowered = task.lower()
        subtasks: list[SubTask] = []

        def add(description: str, role: str) -> None:
            subtasks.append(SubTask(description=description, role=role))

        if any(k in lowered for k in ("review", "ревью", "проанализ", "analyze")):
            add("Explore project structure and key modules", "explorer")
            add("Review code for bugs and quality issues", "reviewer")
            add("Review project for security issues", "security")
        if any(k in lowered for k in ("test", "тест")):
            add("Discover and run the test suite", "tester")
        if any(k in lowered for k in ("fix", "исправ", "bug", "почин")):
            add("Identify and fix reported defects", "debugger")
        if any(k in lowered for k in ("architectur", "архитект")):
            add("Analyze architecture and dependencies", "architect")
        if not subtasks:
            add(task, "coder")
        if num_agents and len(subtasks) < num_agents:
            add("Additional focused subtask", "coder")
        self._plan = subtasks
        return subtasks

    # -- execution -----------------------------------------------------------
    async def run(self, task: str, num_agents: int | None = None) -> str:
        """Run the plan with sub-agents (parallel for independent tasks)."""
        if self._runner is None:
            raise ValueError("Orchestrator requires a task_runner to execute subtasks")
        plan = self.create_plan(task, num_agents)
        results: dict[str, str] = {}

        # Group into waves respecting dependencies.
        pending = list(plan)
        while pending:
            wave = [t for t in pending if all(dep in results for dep in t.dependencies)]
            if not wave:  # circular dependencies -> run sequentially
                wave = [pending[0]]
            outputs = await asyncio.gather(
                *(self._run_subtask(t) for t in wave), return_exceptions=True
            )
            for subtask, output in zip(wave, outputs):
                if isinstance(output, Exception):
                    subtask.status = "failed"
                    subtask.result = f"Error: {output}"
                else:
                    subtask.status = "done"
                    subtask.result = output
                results[subtask.id] = str(subtask.result)
                pending.remove(subtask)

        return self.synthesize(task, results)

    async def _run_subtask(self, subtask: SubTask) -> str:
        role = get_role(subtask.role) or ROLES["coder"]
        agent = AgentInstance(
            role=subtask.role, task=subtask, max_iterations=role.max_iterations,
            permission_manager=self._inherit_permissions(role),
        )
        self._agents.append(agent)
        if len(self._agents) > self._max_agents:
            agent.status = "failed"
            agent.output = f"Error: max agent limit reached (max={self._max_agents})"
            return agent.output
        agent.status = "running"
        agent.started_at = time.monotonic()
        try:
            output = await asyncio.wait_for(
                self._runner(subtask), timeout=self._agent_timeout
            )
            agent.output = output
            agent.status = "done"
            return output
        except asyncio.TimeoutError:
            agent.status = "timeout"
            agent.output = f"Error: sub-agent timed out after {self._agent_timeout}s"
            return agent.output
        except Exception as exc:  # noqa: BLE001
            agent.status = "failed"
            agent.output = f"Error: {exc}"
            return agent.output
        finally:
            agent.finished_at = time.monotonic()

    def _inherit_permissions(self, role) -> PermissionManager:
        """Sub-agents inherit parent permissions, tightened by the role."""
        base: dict[str, str] = {}
        if self._parent_permissions is not None:
            base = dict(self._parent_permissions.list_permissions())
        base.update(role.permissions)
        return PermissionManager(config=base)

    # -- synthesis -----------------------------------------------------------
    def synthesize(self, task: str, results: dict[str, str]) -> str:
        """Combine sub-agent outputs into a final report."""
        lines = [f"ORCHESTRATOR REPORT — {task}", ""]
        for agent in self._agents:
            mark = "✓" if agent.status == "done" else "✗"
            lines.append(f"{mark} Agent {agent.id} ({agent.role}) — {agent.status}")
            if agent.output:
                lines.append(agent.output[:1500])
            lines.append("")
        return "\n".join(lines)

    def get_status(self) -> dict[str, Any]:
        return {
            "total_agents": len(self._agents),
            "running": sum(1 for a in self._agents if a.status == "running"),
            "done": sum(1 for a in self._agents if a.status == "done"),
            "failed": sum(1 for a in self._agents if a.status in ("failed", "timeout")),
            "max_agents": self._max_agents,
            "max_depth": self._max_depth,
            "plan_size": len(self._plan),
        }
