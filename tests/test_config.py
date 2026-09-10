"""Tests for configuration system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiom.config.config import Config
from axiom.config.defaults import DEFAULT_CONFIG, DEFAULT_PERMISSIONS


class TestDefaults:
    """Test default configuration values."""

    def test_default_permissions_exist(self) -> None:
        assert "filesystem.read" in DEFAULT_PERMISSIONS
        assert "terminal.execute" in DEFAULT_PERMISSIONS
        assert "workspace.outside" in DEFAULT_PERMISSIONS

    def test_workspace_outside_is_deny(self) -> None:
        assert DEFAULT_PERMISSIONS["workspace.outside"] == "deny"

    def test_default_config_has_model(self) -> None:
        assert "model" in DEFAULT_CONFIG
        assert "provider" in DEFAULT_CONFIG["model"]

    def test_default_config_has_agents(self) -> None:
        assert "agents" in DEFAULT_CONFIG
        assert "build" in DEFAULT_CONFIG["agents"]
        assert "plan" in DEFAULT_CONFIG["agents"]
        assert "review" in DEFAULT_CONFIG["agents"]


class TestConfig:
    """Test Config class."""

    def test_config_loads_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        config = Config()
        assert config.model_config is not None
        assert config.permissions is not None

    def test_config_get_nested(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        config = Config()
        provider = config.get("model", "provider")
        assert provider is not None

    def test_config_get_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        config = Config()
        result = config.get("nonexistent", "path", default="fallback")
        assert result == "fallback"

    def test_config_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        config = Config()
        config.set("model", "temperature", 0.5)
        assert config.get("model", "temperature") == 0.5

    def test_config_env_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("AXIOM_MODEL", "test-model")
        config = Config()
        assert config.get("model", "model") == "test-model"

    def test_config_to_dict(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        config = Config()
        data = config.to_dict()
        assert isinstance(data, dict)
        assert "model" in data
