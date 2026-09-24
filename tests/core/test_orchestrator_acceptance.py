"""Acceptance: /orchestrate bug-fix scenario through the real pipeline."""
from __future__ import annotations

from axiom.core.ollama import StreamChunk, ToolCallRequest
from tests.core.test_orchestrator_runtime_a import _fake_transport, _session, _stub_verification


async def test_acceptance_orchestrate_bugfix(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "buggy.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    session = _session(tmp_path, monkeypatch, ws)

    def _behavior(last_user: str, kwargs):
        names = [t.get("function", {}).get("name", "") for t in (kwargs.get("tools") or [])]
        if "Review the specialized" in last_user:
            yield StreamChunk(content='{"approved": true, "reason": "fix verified",'
                                      ' "issues": [], "required_changes": []}', done=True)
            return
        if "edit_file" in names:
            yield StreamChunk(tool_calls=[ToolCallRequest(
                name="edit_file",
                arguments={"path": "buggy.py", "old_text": "return a - b",
                           "new_text": "return a + b"})])
            yield StreamChunk(content="fixed add()", done=True)
            return
        if "run_command" in names:
            yield StreamChunk(tool_calls=[ToolCallRequest(
                name="run_command", arguments={"command": "python -m compileall -q buggy.py"})])
            yield StreamChunk(content="compile ok", done=True)
            return
        yield StreamChunk(content="report done", done=True)

    _fake_transport(monkeypatch, _behavior)

    async def _compile_only():
        from axiom.core.verify import VerificationLoop, VerifyStep

        loop = VerificationLoop(runner=session._verification_runner)
        report = await loop.run([VerifyStep("build", "python -m compileall -q buggy.py")])
        return {"ok": report.ok, "summary": report.summary(), "errors": list(report.errors)}

    session._run_orchestration_verification = _compile_only  # type: ignore[method-assign]
    out = await session.run_orchestrated("оркестратор: найди баг в buggy.py, исправь и проверь",
                                         limit=5)
    assert (ws / "buggy.py").read_text(encoding="utf-8").count("return a + b") == 1
    assert out["approved"] is True
    assert out["completed"] is True
    assert out["verification"]["ok"] is True
    assert session.busy is False
    assert _stub_verification is not None
