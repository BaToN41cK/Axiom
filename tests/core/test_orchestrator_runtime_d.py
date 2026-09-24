"""Runtime regression part D: live worker tool events in the shared trajectory.

Workers run against an isolated trajectory, but their real tool activity must
hit the orchestration trajectory the moment it happens — that is what the
Desktop live progress feed consumes while /orchestrate is still running.
"""
from __future__ import annotations

from tests.core.test_orchestrator_runtime_a import _fake_transport, _session, _stub_verification


async def test_runtime_worker_tool_events_are_live_and_not_duplicated(tmp_path, monkeypatch):
    from axiom.core.agent import Agent
    from axiom.core.events import ContentChunk, ReasoningChunk, ToolCallEvent, ToolResultEvent
    from axiom.core.ollama import StreamChunk

    session = _session(tmp_path, monkeypatch)
    _stub_verification(session)
    _fake_transport(monkeypatch, lambda text, kw: [StreamChunk(content="ok", done=True)])

    runs = {"count": 0}

    async def _run(self, history, model, **kwargs):
        runs["count"] += 1
        # A child-trajectory entry written by the real agent during its run:
        # the end-of-run merge must still copy it back as `subagent.*`.
        self._trajectory.append("policy.mode", "mode=auto", actor="system")
        yield ReasoningChunk(text="Сначала проверю требования")
        yield ContentChunk(text="Изучаю структуру проекта")
        yield ToolCallEvent(name="write_file",
                            arguments={"path": "index.html", "content": "<html>"})
        yield ToolResultEvent(name="write_file", ok=True, content="written",
                              duration_ms=5)
        yield ContentChunk(text="Готово")

    monkeypatch.setattr(Agent, "run", _run)
    out = await session.run_orchestrated("оркестратор: создай index.html", limit=5)

    assert out["approved"] is True
    # four workers + one reviewer, no rework (reviewer approves)
    assert runs["count"] == 5

    calls = [e for e in session.trajectory.events if e.kind == "subagent.tool.call"]
    results = [e for e in session.trajectory.events if e.kind == "subagent.tool.result"]
    # live records exist and the end-of-run child merge does not duplicate them
    assert len(calls) == 5
    assert len(results) == 5
    assert {e.actor for e in calls} == {"analyst", "coder", "debugger", "tester", "reviewer"}
    # the call carries its target, the result carries the honest outcome
    coder_call = next(e for e in calls if e.actor == "coder")
    assert coder_call.summary == "write_file index.html"
    assert coder_call.data["arguments"]["path"] == "index.html"
    assert all(e.data.get("ok") is True and e.data.get("duration_ms") == 5
               for e in results)
    # the exact model/provider every specialist calls is visible before the
    # first token (the final reply arrives minutes later)
    models = [e for e in session.trajectory.events if e.kind == "subagent.model"]
    assert len(models) == 5
    assert {e.actor for e in models} == {"analyst", "coder", "debugger", "tester", "reviewer"}
    assert all(e.summary == "ollama/test-model:latest" for e in models)
    # live reasoning and prose of every worker: flushed at the tool call and
    # again at run end — never duplicated by the child-trajectory merge
    reasons = [e for e in session.trajectory.events if e.kind == "subagent.reasoning"]
    answers = [e for e in session.trajectory.events if e.kind == "subagent.answer"]
    assert len(reasons) == 5
    assert all("Сначала проверю требования" in e.summary for e in reasons)
    assert len(answers) == 10
    assert sum("Изучаю структуру проекта" in e.summary for e in answers) == 5
    assert sum(e.summary == "Готово" for e in answers) == 5
    # full text lives in data for the trajectory viewer, summary is the preview
    assert all(e.data.get("text") for e in reasons)
    # other child events still merge back as subagent.*
    kinds = {e.kind for e in session.trajectory.events}
    assert "subagent.policy.mode" in kinds
