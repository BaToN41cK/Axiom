"""Runtime regression part B: mutation, rework bounds, verification."""
from __future__ import annotations

import json

from axiom.core.orchestrator import Orchestrator
from tests.core.test_orchestrator_runtime_a import _fake_transport, _session, _stub_verification


async def test_runtime_file_mutation(tmp_path, monkeypatch):
    from axiom.core.ollama import StreamChunk, ToolCallRequest

    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "fix.txt"
    target.write_text("before", encoding="utf-8")
    session = _session(tmp_path, monkeypatch, workspace)
    _stub_verification(session)

    def _behavior(last_user: str, kwargs):
        names = [t.get("function", {}).get("name", "") for t in (kwargs.get("tools") or [])]
        if "Review the specialized" in last_user:
            yield StreamChunk(content='{"approved": true, "reason": "ok",'
                                      ' "issues": [], "required_changes": []}', done=True)
            return
        if "edit_file" in names:
            yield StreamChunk(tool_calls=[ToolCallRequest(
                name="edit_file",
                arguments={"path": "fix.txt", "old_text": "before", "new_text": "after"})])
            yield StreamChunk(content="edited", done=True)
            return
        yield StreamChunk(content="report", done=True)

    _fake_transport(monkeypatch, _behavior)
    out = await session.run_orchestrated("оркестратор: исправь fix.txt", limit=5)
    assert target.read_text(encoding="utf-8") == "after"
    assert out["approved"] is True
    assert any("edit_file" in (e.summary or "")
               or "edit_file" in json.dumps(e.data, ensure_ascii=False)
               for e in session.trajectory.events)


async def test_runtime_rework_bounded():
    seen: list[str] = []

    async def _runner(**kwargs):
        agent = str(kwargs.get("agent"))
        seen.append(agent)
        if agent == "reviewer":
            return {"content": "REWORK: still broken"}
        return {"content": "partial work"}

    out = await Orchestrator().run("оркестратор: сделай код", runner=_runner,
                                   parallel=True, limit=2, max_iterations=10,
                                   force_orchestrated=True)
    assert [s for s in seen if s == "reviewer"] == ["reviewer"] * 3
    assert out["approved"] is False
    assert out["iterations"] == 3


async def test_runtime_rework_reruns():
    attempts: list[str] = []
    state = {"n": 0}

    async def _runner(**kwargs):
        agent = str(kwargs.get("agent"))
        if agent == "reviewer":
            state["n"] += 1
            if state["n"] == 1:
                return {"content": "REWORK: add missing check"}
            return {"content": "APPROVED"}
        attempts.append(str(kwargs.get("task") or ""))
        if any("REVIEW REQUEST" in a for a in attempts):
            return {"content": "fixed after review"}
        return {"content": "first attempt"}

    out = await Orchestrator().run("оркестратор: сделай код", runner=_runner,
                                   parallel=True, limit=1, max_iterations=3,
                                   force_orchestrated=True)
    assert out["approved"] is True
    assert any("REVIEW REQUEST" in a for a in attempts)
    assert any("fixed after review" in str(r.get("content")) for r in out["results"])


async def test_runtime_verification_honest():
    async def _runner(**kwargs):
        if str(kwargs.get("agent")) == "reviewer":
            return {"content": "APPROVED"}
        return {"content": "done"}

    async def _bad_verify():
        return {"ok": False, "summary": "verify FAILED", "errors": ["test failed"]}

    out = await Orchestrator().run("оркестратор: сделай код", runner=_runner,
                                   parallel=True, limit=1, force_orchestrated=True,
                                   verifier=_bad_verify)
    assert out["approved"] is True
    assert out["completed"] is False
    assert out["verification"]["ok"] is False
