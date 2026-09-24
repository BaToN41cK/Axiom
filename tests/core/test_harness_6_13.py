"""Тесты Harness 6-13: bus, trajectory, orchestrator."""
from __future__ import annotations

from axiom.core.bus import EventBus
from axiom.core.orchestrator import Orchestrator
from axiom.core.trajectory import Trajectory
from axiom.core.trajectory_store import TrajectoryStore


def test_event_bus_emit_and_subscribe():
    bus = EventBus()
    seen: list[dict] = []
    bus.subscribe("agent.step", seen.append)
    bus.emit("agent.step", {"agent": "coder"})
    assert len(seen) == 1
    assert bus.emitted == 1


async def test_event_bus_async_subscriber():
    bus = EventBus()
    seen: list[dict] = []

    async def _handler(payload: dict) -> None:
        seen.append(payload)

    bus.subscribe("tool.before", _handler)
    await bus.emit_async("tool.before", {"tool": "read_file"})
    assert len(seen) == 1


def test_trajectory_append_timeline_usage_and_search():
    traj = Trajectory(actor="orchestrator")
    traj.append("user", "fix bug", data={"usage": {"input_tokens": 10, "output_tokens": 5}})
    traj.append("tool.call", "read_file main.py")
    assert len(traj.events) == 2
    assert traj.usages()["input_tokens"] == 10
    assert len(traj.search("read_file")) == 1
    assert traj.replay() == traj.timeline()


def test_trajectory_fork_keeps_history_and_marks_parent():
    traj = Trajectory(actor="orchestrator")
    traj.append("user", "original task")
    child = traj.fork()
    assert child.run_id != traj.run_id
    assert child.events[-1].kind == "trajectory.fork"


def test_trajectory_store_save_and_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("AXIOM_HOME", str(tmp_path))
    store = TrajectoryStore()
    traj = Trajectory(actor="orchestrator")
    traj.append("user", "hello")
    path = store.save(traj)
    assert path.exists()
    resumed = store.resume(traj.run_id)
    assert resumed is not None
    assert resumed.events[-1].kind == "trajectory.resume"


async def test_orchestrator_plans_debug_and_runs_subagents():
    orch = Orchestrator()
    plan = orch.plan("Исправь баг запуска проекта")
    assert plan.mode == "debug"

    async def _runner(**kwargs):
        return {"ok": True, "agent": kwargs.get("agent")}

    out = await orch.run("Исправь баг запуска проекта", runner=_runner)
    assert out["mode"] == "debug"
    assert all(r["status"] == "done" for r in out["results"])


def test_orchestrator_selects_at_most_five_roles_and_defines_done():
    plan = Orchestrator().plan("оркестратор: coder, debugger, researcher и tester")
    assert len(plan.agents) <= 5
    assert plan.definition_of_done
    assert "analyst" in plan.agents


def test_orchestrator_tools_include_analyst_scope():
    assert "read_file" in Orchestrator().tools_for("analyst")


async def test_orchestrator_reviewer_can_request_rework():
    calls: list[str] = []

    async def _runner(**kwargs):
        calls.append(str(kwargs.get("agent")))
        if kwargs.get("agent") == "reviewer":
            return {"content": "REWORK: add a failing test"}
        return {"content": "done"}

    out = await Orchestrator().run("сделай код", runner=_runner)
    assert out["approved"] is False
    assert "REWORK" in out["review"]
    assert "reviewer" in calls


async def test_orchestrator_rework_reruns_workers_and_verifies():
    calls: list[str] = []
    reviews = 0

    async def _runner(**kwargs):
        nonlocal reviews
        agent = str(kwargs.get("agent"))
        calls.append(agent)
        if agent == "reviewer":
            reviews += 1
            if reviews == 1:
                return {"approved": False, "reason": "missing test",
                        "issues": ["no regression test"],
                        "required_changes": ["add regression test"]}
            return {"approved": True, "reason": "checks passed"}
        return {"agent": agent, "content": f"{agent} completed"}

    async def _verify():
        return {"ok": True, "summary": "pytest: pass"}

    out = await Orchestrator().run(
        "исправь код", runner=_runner, parallel=True, limit=5,
        max_iterations=3, force_orchestrated=True, verifier=_verify,
    )
    assert out["approved"] is True
    assert out["verification"] == {"ok": True, "summary": "pytest: pass"}
    assert calls.count("coder") == 2
    assert calls.count("reviewer") == 2
    assert any(e.kind == "verification.completed" for e in out["trajectory"].events)


async def test_orchestrator_rework_is_bounded():
    calls: list[str] = []

    async def _runner(**kwargs):
        agent = str(kwargs.get("agent"))
        calls.append(agent)
        if agent == "reviewer":
            return {"approved": False, "reason": "still broken",
                    "required_changes": ["fix it"]}
        return {"content": "attempt"}

    out = await Orchestrator().run(
        "исправь код", runner=_runner, parallel=True, limit=5,
        max_iterations=3, force_orchestrated=True,
    )
    assert out["approved"] is False
    assert calls.count("reviewer") == 3
    assert len([e for e in out["trajectory"].events if e.kind == "orchestrator.review"]) == 3


def test_orchestrator_emits_planning_and_completion_events():
    from axiom.core.bus import EventBus

    seen: list[dict] = []
    bus = EventBus()
    bus.subscribe("orchestration.planned", seen.append)

    async def _runner(**kwargs):
        return {"content": "ok"}

    out = __import__("asyncio").run(Orchestrator(bus=bus).run(
        "сделай код", runner=_runner, force_orchestrated=True,
    ))
    assert out["mode"] == "orchestrated"
    assert any(item.get("event") == "orchestration.planned" for item in seen)


    orch = Orchestrator()
    assert "web_search" in orch.tools_for("researcher")
    assert "write_file" not in orch.tools_for("researcher")
    assert "run_command" in orch.tools_for("coder")


def test_context_engine_builds_messages_with_files(tmp_path):
    from axiom.core.context_engine import ContextEngine
    engine = ContextEngine()
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    built = engine.build("fix bug", [{"role": "user", "content": "fix bug"}],
                         system_prompt="base", workspace_root=root,
                         file_paths=["main.py"])
    assert built.messages[0]["role"] == "system"
    assert "main.py" in built.messages[0]["content"]


async def test_context_engine_compress_keeps_source_intact():
    from axiom.core.context_engine import ContextEngine
    engine = ContextEngine()
    messages = [{"role": "user", "content": f"msg {i} " + ("x" * 50)} for i in range(10)]

    async def _summarizer(text: str) -> str:
        return "summary of old"

    compacted, changed = await engine.compress(messages, _summarizer, preserve_count=3)
    assert changed is True
    assert len(compacted) < len(messages)
    assert len(messages) == 10


async def test_verification_loop_stops_on_first_failure():
    from axiom.core.verify import VerificationLoop, VerifyStep
    calls: list[str] = []

    async def _runner(**kwargs):
        calls.append(kwargs.get("step", ""))
        if kwargs.get("step") == "test":
            return {"ok": False, "output": "1 failed"}
        return {"ok": True, "output": "ok"}

    loop = VerificationLoop(runner=_runner)
    report = await loop.run([VerifyStep("build", "b"), VerifyStep("test", "t"),
                             VerifyStep("lint", "l")])
    assert report.ok is False
    assert [s.name for s in report.steps] == ["build", "test"]


def test_sandbox_levels_and_policies():
    from axiom.core.sandbox import Sandbox, SandboxLevel, SandboxPolicy
    box = Sandbox()
    assert box.decide("read_file") == "auto"
    assert box.decide("delete_file") == "ask"
    box.set_policy(SandboxLevel.DELETE, SandboxPolicy.DENY)
    assert box.allows("delete_file") is False


async def test_agent_emits_bus_and_trajectory_events():
    from axiom.core.agent import Agent
    from axiom.core.bus import EventBus as _Bus
    from axiom.core.config import Config
    from axiom.core.models import ModelInfo
    from axiom.core.state_machine import GenerationStateMachine
    from axiom.core.tools.base import ToolDefinition, ToolPermission, ToolResult
    from axiom.core.tools.registry import ToolRegistry
    from axiom.core.trajectory import Trajectory as _Traj

    async def _echo(**kwargs) -> ToolResult:
        return ToolResult(name="echo", ok=True, content="hi")

    registry = ToolRegistry()
    registry.register(ToolDefinition(name="echo", description="e",
                                     permission=ToolPermission.ALWAYS), _echo)

    class _Client:
        async def chat(self, *args, **kwargs):
            from axiom.core.ollama import StreamChunk, ToolCallRequest
            yield StreamChunk(tool_calls=[ToolCallRequest(name="echo", arguments={})])
            yield StreamChunk(content="done", done=True,
                              metrics={"eval_count": 2, "prompt_eval_count": 3})

    bus = _Bus()
    traj = _Traj(actor="tester")
    agent = Agent(_Client(), config=Config(), registry=registry,
                  machine=GenerationStateMachine(), bus=bus, trajectory=traj)  # type: ignore[arg-type]
    events = [e async for e in agent.run([{"role": "user", "content": "hi"}],
                                         ModelInfo(name="m"))]
    assert any(getattr(e, "type", "") == "content" for e in events)
    assert bus.emitted >= 2
    assert any(e.kind == "tool.call" for e in traj.events)

    orch = Orchestrator()
    assert "web_search" in orch.tools_for("researcher")
    assert "write_file" not in orch.tools_for("researcher")
    assert "run_command" in orch.tools_for("coder")
