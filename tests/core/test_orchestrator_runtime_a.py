"""Runtime regression: real pipeline, faked model transport only."""
from __future__ import annotations

from pathlib import Path

from axiom.core.chat import ChatSession
from axiom.core.config import Config
from axiom.core.history import HistoryStore
from axiom.core.models import ModelInfo
from axiom.core.tools.meta import tools_for_agent


def _session(tmp_path: Path, monkeypatch, workspace: Path | None = None) -> ChatSession:
    monkeypatch.setenv("AXIOM_HOME", str(tmp_path / "home"))
    cfg = Config(model="test-model:latest")
    cfg.save_history = False
    session = ChatSession(config=cfg, history_store=HistoryStore(directory=tmp_path / "h"))
    session.active_model = ModelInfo(name="test-model:latest", capabilities=["tools"])
    if workspace is not None:
        session.set_workspace(str(workspace))
    return session


def _fake_transport(monkeypatch, behavior) -> None:
    async def _fake_chat(self, model, messages, **kwargs):
        history = list(messages or [])
        last = str(history[-1].get("content", "")) if history else ""
        for chunk in behavior(last, kwargs):
            yield chunk

    monkeypatch.setattr("axiom.core.ollama.OllamaClient.chat", _fake_chat)
    monkeypatch.setattr("axiom.core.providers.runtime.ProviderChatClient.chat", _fake_chat)


def _stub_verification(session) -> None:
    """Session-level orchestration must not run the repo-wide pytest in unit tests."""

    async def _ok():
        return {"ok": True, "summary": "verify PASSED [stub]", "errors": []}

    session._run_orchestration_verification = _ok  # type: ignore[method-assign]


async def test_runtime_basic_flow(tmp_path, monkeypatch):
    from axiom.core.ollama import StreamChunk

    session = _session(tmp_path, monkeypatch)
    seen: list[str] = []
    orig = session._subagent_runner

    async def _spy(**kwargs):
        seen.append(str(kwargs.get("agent")))
        return await orig(**kwargs)

    monkeypatch.setattr(session, "_subagent_runner", _spy)
    _stub_verification(session)
    _fake_transport(monkeypatch, lambda text, kw: [StreamChunk(content="report", done=True)])
    out = await session.run_orchestrated("оркестратор: проанализируй задачу", limit=5)
    assert out["mode"] == "orchestrated"
    assert len(out["results"]) == 4
    assert {"analyst", "coder", "debugger", "tester"} <= set(seen)
    assert out["approved"] is True
    kinds = {e.kind for e in session.trajectory.events}
    assert "orchestrator.plan" in kinds
    assert any(k.startswith("subagent.") for k in kinds)
    assert any(e.kind == "orchestrator.review" for e in session.trajectory.events)


async def test_runtime_role_scope():
    assert "write_file" not in tools_for_agent("analyst")
    assert "write_file" not in tools_for_agent("reviewer")
    assert "write_file" in tools_for_agent("coder")
    assert "run_command" in tools_for_agent("tester")
    assert "read_file" in tools_for_agent("analyst")
