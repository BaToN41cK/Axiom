"""Orchestrator — управляет агентами, а не просто шлёт запрос модели (п.7).

План: analyze -> select agents -> delegate (subagents) -> verify -> result.
Саб­агенты здесь — записи trajectory + делегирование через колбэк раннера,
чтобы Core не зависел от конкретной модели.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from axiom.core.agents import AgentRegistry
from axiom.core.bus import (
    AGENT_CREATED,
    AGENT_FAILED,
    AGENT_STARTED,
    AGENT_STEP,
    EventBus,
)
from axiom.core.tools.meta import resolve_tools_for_task, tools_for_agent
from axiom.core.trajectory import Trajectory

SubagentRunner = Callable[..., Awaitable[dict]]


@dataclass
class Subagent:
    id: str
    agent: str
    task: str
    status: str = "pending"
    result: dict = field(default_factory=dict)


@dataclass
class OrchestratorPlan:
    mode: str = "chat"
    agents: list[str] = field(default_factory=list)
    subagents: list[Subagent] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


class Orchestrator:
    """Планировщик поверх AgentRegistry + Trajectory + EventBus."""

    def __init__(self, agents: AgentRegistry | None = None, bus: EventBus | None = None) -> None:
        self.agents = agents or AgentRegistry()
        self.bus = bus or EventBus()

    def plan(self, text: str) -> OrchestratorPlan:
        lowered = (text or "").lower()
        if any(k in lowered for k in ("исправ", "fix", "bug", "баг", "error", "ошибк", "падает", "debug")):
            mode = "debug"
            agents = ["coder", "debugger", "tester", "reviewer"]
        elif any(k in lowered for k in ("review", "проверь", "pr", "ревью")):
            mode = "review"
            agents = ["reviewer", "security"]
        elif any(k in lowered for k in ("research", "найди", "изучи", "что делает", "документ", "research")):
            mode = "research"
            agents = ["researcher", "architect"]
        elif any(k in lowered for k in ("test", "тест", "pytest")):
            mode = "test"
            agents = ["tester", "debugger"]
        elif any(k in lowered for k in ("refactor", "рефактор", "implement", "реализуй", "добавь", "code", "код")):
            mode = "code"
            agents = ["architect", "coder", "tester", "reviewer"]
        else:
            mode = "chat"
            agents = ["researcher"]
        agents = [a for a in agents if self.agents.get(a) is not None]
        tools = resolve_tools_for_task(text)
        subs = [Subagent(id=f"{a}-1", agent=a, task=text) for a in agents]
        return OrchestratorPlan(mode=mode, agents=agents, subagents=subs, tools=tools)

    def tools_for(self, agent_id: str, task: str = "") -> list[str]:
        base = list(tools_for_agent(agent_id)) or resolve_tools_for_task(task)
        # Агент получает только свои tools (п.8).
        return base

    async def run(
        self,
        text: str,
        trajectory: Trajectory | None = None,
        runner: SubagentRunner | None = None,
        *,
        parallel: bool = False,
        limit: int = 4,
    ) -> dict:
        traj = trajectory or Trajectory(actor="orchestrator")
        started = time.perf_counter()
        plan = self.plan(text)
        traj.append("orchestrator.plan", f"mode={plan.mode} agents={','.join(plan.agents)}",
                    actor="orchestrator", data={"mode": plan.mode, "agents": plan.agents})
        self.bus.emit(AGENT_STARTED, {"agent": "orchestrator", "mode": plan.mode, "run_id": traj.run_id})
        if parallel and runner is not None:
            from axiom.core.parallel import run_parallel

            tasks = [{"agent": sub.agent, "task": sub.task,
                      "tools": self.tools_for(sub.agent, sub.task),
                      "trajectory": traj} for sub in plan.subagents]
            pres = await run_parallel(tasks, runner, limit=limit, trajectory=traj)
            duration_ms = pres.duration_ms
            traj.append("orchestrator.done", f"mode={plan.mode} parallel={len(pres.results)}",
                        actor="orchestrator", data={"duration_ms": duration_ms})
            return {"run_id": traj.run_id, "mode": plan.mode, "agents": plan.agents,
                    "results": pres.results, "merged": pres.merged,
                    "duration_ms": duration_ms, "trajectory": traj}
        results: list[dict] = []
        for sub in plan.subagents:
            self.bus.emit(AGENT_CREATED, {"agent": sub.agent, "task": sub.task, "run_id": traj.run_id})
            traj.append("agent.start", f"{sub.agent}: {sub.task[:120]}", actor=sub.agent)
            sub.status = "running"
            self.bus.emit(AGENT_STEP, {"agent": sub.agent, "step": "start", "run_id": traj.run_id})
            try:
                if runner is not None:
                    out = await runner(agent=sub.agent, task=sub.task,
                                       tools=self.tools_for(sub.agent, sub.task),
                                       trajectory=traj)
                    sub.result = dict(out or {})
                else:
                    sub.result = {"agent": sub.agent, "task": sub.task,
                                  "tools": self.tools_for(sub.agent, sub.task),
                                  "note": "no runner attached"}
                sub.status = "done"
                traj.append("agent.done", f"{sub.agent} done", actor=sub.agent, data=sub.result)
                self.bus.emit(AGENT_STEP, {"agent": sub.agent, "step": "done", "run_id": traj.run_id})
            except Exception as exc:
                sub.status = "failed"
                sub.result = {"error": f"{type(exc).__name__}: {exc}"}
                traj.append("agent.failed", str(exc), actor=sub.agent, data=sub.result)
                self.bus.emit(AGENT_FAILED, {"agent": sub.agent, "error": str(exc), "run_id": traj.run_id})
            results.append({"agent": sub.agent, "status": sub.status, **sub.result})
        duration_ms = int((time.perf_counter() - started) * 1000)
        traj.append("orchestrator.done", f"mode={plan.mode} subagents={len(results)}",
                    actor="orchestrator", data={"duration_ms": duration_ms})
        return {"run_id": traj.run_id, "mode": plan.mode, "agents": plan.agents,
                "results": results, "duration_ms": duration_ms, "trajectory": traj}
