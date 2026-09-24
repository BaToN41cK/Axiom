"""Runtime regression part C: isolation, external model, busy lock."""
from __future__ import annotations

from axiom.core.models import ModelInfo
from tests.core.test_orchestrator_runtime_a import _fake_transport, _session, _stub_verification


async def test_runtime_isolation(tmp_path, monkeypatch):
    from axiom.core.agent import Agent
    from axiom.core.events import ContentChunk

    session = _session(tmp_path, monkeypatch)
    agents: list = []

    async def _run(self, history, model, **kwargs):
        agents.append(self)
        yield ContentChunk(text="x")

    monkeypatch.setattr(Agent, "run", _run)
    _stub_verification(session)
    out = await session.run_orchestrated("оркестратор: проверь изоляцию", limit=5)
    assert len(agents) == 5
    assert len({id(a) for a in agents}) == 5
    assert len({id(a._config) for a in agents}) == 5
    assert len({id(a._registry) for a in agents}) == 5
    assert len({id(a._machine) for a in agents}) == 5
    assert len({id(a._trajectory) for a in agents}) == 5
    assert len({id(a._permissions) for a in agents}) == 5
    assert len({id(a._sandbox) for a in agents}) == 5
    assert len({id(a._bus) for a in agents}) == 5
    assert out["approved"] is True


async def test_runtime_external_model(tmp_path, monkeypatch):
    from axiom.core.agent import Agent
    from axiom.core.ollama import StreamChunk
    from axiom.core.router import RouteTarget

    session = _session(tmp_path, monkeypatch)
    session.router.config.primary = RouteTarget("openai_compatible", "deepseek/test", reason="t")
    session.active_model = ModelInfo(name="deepseek/test", capabilities=["tools"])
    seen_models: list[str] = []
    orig_run = Agent.run

    async def _spy_run(self, history, model, **kwargs):
        seen_models.append(model.name)
        async for event in orig_run(self, history, model, **kwargs):
            yield event

    monkeypatch.setattr(Agent, "run", _spy_run)
    _stub_verification(session)
    _fake_transport(monkeypatch, lambda text, kw: [StreamChunk(content="ok", done=True)])
    out = await session.run_orchestrated("оркестратор: проверь модель", limit=2)
    assert seen_models and all(m == "deepseek/test" for m in seen_models)
    assert all(r.get("provider_id") == "openai_compatible" for r in out["results"])


async def test_runtime_busy_released(tmp_path, monkeypatch):
    from axiom.core.ollama import StreamChunk

    session = _session(tmp_path, monkeypatch)
    _stub_verification(session)
    _fake_transport(monkeypatch, lambda text, kw: [StreamChunk(content="ok", done=True)])
    assert session.busy is False
    out = await session.run_orchestrated("оркестратор: быстрая задача", limit=1)
    assert session.busy is False
    assert out["approved"] is True


async def test_runtime_cancel_stops_orchestration(tmp_path, monkeypatch):
    """Esc/stop must really stop the workers and release the busy lock."""
    import asyncio

    session = _session(tmp_path, monkeypatch)
    _stub_verification(session)
    started = asyncio.Event()

    async def _blocking_runner(**kwargs):
        started.set()
        await asyncio.Event().wait()  # blocks until the orchestration is cancelled
        return {"agent": kwargs.get("agent"), "content": ""}

    monkeypatch.setattr(session, "_subagent_runner", _blocking_runner)
    task = asyncio.create_task(
        session.run_orchestrated("оркестратор: долгая задача", limit=2))
    await asyncio.wait_for(started.wait(), timeout=5)
    assert session.busy is True
    assert session.cancel() is True
    out = await asyncio.wait_for(task, timeout=5)
    assert out.get("cancelled") is True
    assert out.get("completed") is False
    assert session.busy is False
    kinds = [e.kind for e in session.trajectory.events]
    assert "orchestration.cancelled" in kinds
