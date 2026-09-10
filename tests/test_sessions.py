"""Tests for SessionManager (SQLite-backed sessions)."""

from __future__ import annotations

from pathlib import Path

import pytest

from axiom.session import SessionManager, StoredMessage


@pytest.fixture
def manager(tmp_path: Path, monkeypatch) -> SessionManager:
    monkeypase = monkeypatch
    monkeypase.setenv("HOME", str(tmp_path))
    monkeypase.setenv("USERPROFILE", str(tmp_path))
    monkeypase.setenv("AXIOM_HOME", str(tmp_path))
    db = tmp_path / "sessions.db"
    import os

    os.makedirs(tmp_path / ".axiom" / "sessions", exist_ok=True)
    return SessionManager(db_path=db)


class TestSessionManager:
    def test_create_and_get(self, manager: SessionManager) -> None:
        session = manager.create_session("My task", model="GPT-OSS-120B")
        assert session.title == "My task"
        fetched = manager.get_session(session.id)
        assert fetched is not None
        assert fetched.id == session.id
        assert fetched.model == "GPT-OSS-120B"

    def test_list_and_delete(self, manager: SessionManager) -> None:
        a = manager.create_session("A")
        b = manager.create_session("B")
        sessions = manager.list_sessions()
        assert len(sessions) >= 2
        assert manager.delete_session(a.id) is True
        assert manager.get_session(a.id) is None
        assert manager.get_session(b.id) is not None

    def test_messages_roundtrip(self, manager: SessionManager) -> None:
        session = manager.create_session("conv")
        manager.add_message(session.id, StoredMessage(role="user", content="hi"))
        manager.add_message(
            session.id,
            StoredMessage(role="assistant", content="hello", tool_calls=[
                {"id": "c1", "name": "read_file", "arguments": {"path": "x"}}
            ]),
        )
        msgs = manager.get_messages(session.id)
        assert len(msgs) == 2
        assert msgs[1].tool_calls[0]["name"] == "read_file"

    def test_update_summary(self, manager: SessionManager) -> None:
        session = manager.create_session("s")
        manager.update_session(session.id, summary="compacted", state="complete")
        fetched = manager.get_session(session.id)
        assert fetched.summary == "compacted"
        assert fetched.state == "complete"
