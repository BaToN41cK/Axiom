"""Tests for new Axiom modules."""

from __future__ import annotations

import pytest

from axiom.models.manager import ModelManager, ModelInfo, ProviderInfo
from axiom.agent_roles import get_role, list_roles, ROLES
from axiom.orchestrator import Orchestrator, SubTask, AgentInstance
from axiom.session import SessionManager, Session


class TestModelManager:
    """Test ModelManager."""

    def test_init(self):
        mm = ModelManager()
        providers = mm.list_providers()
        assert len(providers) >= 2
        assert any(p.name == "ollama" for p in providers)
        assert any(p.name == "openai_compatible" for p in providers)

    def test_get_provider(self):
        mm = ModelManager()
        provider = mm.get_provider("ollama")
        assert provider is not None
        assert provider.name == "ollama"
        assert provider.requires_api_key is False

    def test_get_current_model(self):
        mm = ModelManager({"model": {"model": "test-model", "provider": "ollama"}})
        model = mm.get_current_model()
        assert model is not None
        assert model.id == "test-model"


class TestAgentRoles:
    """Test agent roles."""

    def test_list_roles(self):
        roles = list_roles()
        assert "coder" in roles
        assert "planner" in roles
        assert "reviewer" in roles
        assert "orchestrator" in roles

    def test_get_role(self):
        role = get_role("coder")
        assert role is not None
        assert role.name == "coder"
        assert len(role.tools) > 0

    def test_role_permissions(self):
        role = get_role("planner")
        assert role is not None
        assert role.permissions.get("filesystem.write") == "deny"


class TestOrchestrator:
    """Test orchestrator."""

    def test_init(self):
        orch = Orchestrator(max_agents=4, max_depth=2)
        assert orch._max_agents == 4
        assert orch._max_depth == 2

    def test_create_plan(self):
        orch = Orchestrator()
        tasks = orch.create_plan("analyze backend and frontend")
        assert len(tasks) >= 1

    def test_get_status(self):
        orch = Orchestrator()
        status = orch.get_status()
        assert "total_agents" in status


class TestSessionManager:
    """Test SessionManager."""

    def test_create_session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        sm = SessionManager()
        session = sm.create_session("Test Session")
        assert session.title == "Test Session"
        assert len(session.id) > 0

    def test_get_session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        sm = SessionManager()
        session = sm.create_session("Test")
        retrieved = sm.get_session(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id

    def test_list_sessions(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        sm = SessionManager()
        sm.create_session("Test 1")
        sm.create_session("Test 2")
        sessions = sm.list_sessions()
        assert len(sessions) >= 2

    def test_delete_session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        sm = SessionManager()
        session = sm.create_session("Test")
        assert sm.delete_session(session.id) is True
        assert sm.get_session(session.id) is None
