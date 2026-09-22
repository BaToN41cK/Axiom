"""Tests for ProfileManager (axiom.core.profiles)."""

from __future__ import annotations

from pathlib import Path

import pytest

from axiom.core.profiles import ProfileManager, DEFAULT_PROFILES


class TestDefaults:
    def test_default_profiles_loaded(self):
        mgr = ProfileManager()
        assert len(mgr.names) >= 5
        assert "Default" in mgr.names
        assert mgr.active_name == "Default"

    def test_get_profile(self):
        mgr = ProfileManager()
        prompt = mgr.get("Default")
        assert prompt is not None
        assert "AXIOM" in prompt

    def test_get_missing(self):
        mgr = ProfileManager()
        assert mgr.get("NonExistent") is None


class TestSelect:
    def test_select_existing(self):
        mgr = ProfileManager()
        assert mgr.select("Programmer") is True
        assert mgr.active_name == "Programmer"
        assert "programming" in mgr.active_prompt.lower()

    def test_select_missing(self):
        mgr = ProfileManager()
        assert mgr.select("Ghost") is False
        assert mgr.active_name == "Default"  # unchanged


class TestAddRemove:
    def test_add_new(self):
        mgr = ProfileManager()
        assert mgr.add("Custom", "You are a custom assistant.") is True
        assert "Custom" in mgr.names
        assert mgr.get("Custom") == "You are a custom assistant."

    def test_add_empty_name_fails(self):
        mgr = ProfileManager()
        assert mgr.add("", "anything") is False
        assert mgr.add("   ", "anything") is False

    def test_update_existing(self):
        mgr = ProfileManager()
        old = mgr.get("Default")
        mgr.add("Default", "Updated prompt.")
        assert mgr.get("Default") == "Updated prompt."

    def test_remove(self):
        mgr = ProfileManager()
        assert mgr.remove("Translator") is True
        assert "Translator" not in mgr.names

    def test_remove_missing(self):
        mgr = ProfileManager()
        assert mgr.remove("Nope") is False

    def test_remove_active_fallsback_to_default(self):
        mgr = ProfileManager()
        mgr.select("Writer")
        mgr.remove("Writer")
        assert mgr.active_name == "Default"


class TestRename:
    def test_rename(self):
        mgr = ProfileManager()
        assert mgr.rename("Default", "Standard") is True
        assert "Standard" in mgr.names
        assert "Default" not in mgr.names

    def test_rename_to_empty(self):
        mgr = ProfileManager()
        assert mgr.rename("Default", "") is False

    def test_rename_missing(self):
        mgr = ProfileManager()
        assert mgr.rename("Ghost", "NewName") is False

    def test_rename_active_updates_active(self):
        mgr = ProfileManager()
        mgr.select("Researcher")
        mgr.rename("Researcher", "ResearchPro")
        assert mgr.active_name == "ResearchPro"


class TestPersistence:
    def test_save_and_load(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        home = tmp_path / "axiom-home"
        monkeypatch.setenv("AXIOM_HOME", str(home))
        mgr = ProfileManager()
        mgr.add("TempProfile", "Temporary assistant.")
        mgr.select("TempProfile")
        mgr2 = ProfileManager()
        assert "TempProfile" in mgr2.names
        assert mgr2.get("TempProfile") == "Temporary assistant."

    def test_reset(self):
        mgr = ProfileManager()
        mgr.add("Custom", "Test")
        mgr.select("Custom")
        mgr.reset()
        assert "Custom" not in mgr.names
        assert mgr.active_name == "Default"


class TestAllProperty:
    def test_all_returns_copy(self):
        mgr = ProfileManager()
        all_profiles = mgr.all
        all_profiles["Default"] = "hacked"
        assert mgr.get("Default") != "hacked"