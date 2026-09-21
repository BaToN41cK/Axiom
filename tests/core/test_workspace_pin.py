"""Tests for pin/unpin and project creation in WorkspaceManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from axiom.core import workspace as ws_module
from axiom.core.workspace import WorkspaceManager


def _make_project(root: Path, name: str) -> Path:
    proj = root / name
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "src").mkdir(exist_ok=True)
    (proj / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    return proj


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the on-disk store to a temp dir so tests are hermetic."""
    store = tmp_path / "workspaces.json"
    monkeypatch.setattr(ws_module, "STORE_PATH", store)


@pytest.fixture()
def mgr() -> WorkspaceManager:
    return WorkspaceManager()


def test_pin_unpin_workspace(mgr: WorkspaceManager, tmp_path: Path) -> None:
    proj_a = _make_project(tmp_path, "proj_a")
    proj_b = _make_project(tmp_path, "proj_b")

    # Initially nothing is pinned
    assert not mgr.is_pinned(str(proj_a))
    assert not mgr.is_pinned(str(proj_b))

    # Pin project A
    assert mgr.pin(str(proj_a))
    assert mgr.is_pinned(str(proj_a))
    assert not mgr.is_pinned(str(proj_b))

    # Pin project B
    assert mgr.pin(str(proj_b))
    assert mgr.is_pinned(str(proj_a))
    assert mgr.is_pinned(str(proj_b))

    # Pin same project again should return False (already pinned)
    assert not mgr.pin(str(proj_a))

    # Unpin project A
    assert mgr.unpin(str(proj_a))
    assert not mgr.is_pinned(str(proj_a))
    assert mgr.is_pinned(str(proj_b))

    mgr.clear()


def test_pinned_projects_list(mgr: WorkspaceManager, tmp_path: Path) -> None:
    proj_a = _make_project(tmp_path, "project_a")
    proj_b = _make_project(tmp_path, "project_b")

    # Remember projects (adds to recents)
    mgr.remember(proj_a)
    mgr.remember(proj_b)

    # Initially no pinned projects
    assert len(mgr.pinned_projects()) == 0

    # Pin both projects
    mgr.pin(str(proj_a))
    mgr.pin(str(proj_b))

    pinned = mgr.pinned_projects()
    assert len(pinned) == 2
    pinned_paths = {p.path for p in pinned}
    assert str(proj_a.resolve()) in pinned_paths
    assert str(proj_b.resolve()) in pinned_paths

    mgr.clear()


def test_create_project(mgr: WorkspaceManager, tmp_path: Path) -> None:
    new_path = tmp_path / "new_project"

    # Create the project directory
    info = mgr.create_project(new_path)

    assert info.path == str(new_path.resolve())
    assert new_path.exists()
    assert new_path.is_dir()

    # The new project should appear in recent
    recent = mgr.recent()
    assert any(p.path == info.path for p in recent)

    mgr.clear()


def test_search_projects(mgr: WorkspaceManager, tmp_path: Path) -> None:
    proj_a = _make_project(tmp_path, "alpha_project")
    proj_b = _make_project(tmp_path, "beta_project")

    mgr.remember(proj_a)
    mgr.remember(proj_b)

    # Search for "alpha"
    results = mgr.search_projects("alpha")
    assert len(results) == 1
    assert results[0].path == str(proj_a.resolve())

    # Search for "beta"
    results = mgr.search_projects("beta")
    assert len(results) == 1
    assert results[0].path == str(proj_b.resolve())

    # Search for non-existent project
    results = mgr.search_projects("nonexistent_project")
    assert len(results) == 0

    mgr.clear()


def test_remove_pinned_from_recents(mgr: WorkspaceManager, tmp_path: Path) -> None:
    proj_a = _make_project(tmp_path, "project_a")

    mgr.remember(proj_a)
    mgr.pin(str(proj_a))

    assert mgr.is_pinned(str(proj_a))

    # Remove should clear from both recents and pinned
    assert mgr.remove(str(proj_a))

    assert not mgr.is_pinned(str(proj_a))
    assert len(mgr.recent()) == 0
    assert len(mgr.pinned_projects()) == 0

    mgr.clear()


def test_create_project_remembered(mgr: WorkspaceManager, tmp_path: Path) -> None:
    new_path = tmp_path / "another_project"

    mgr.create_project(new_path)

    # Project should be in recents and not pinned
    recent = mgr.recent()
    assert len(recent) == 1
    assert recent[0].path == str(new_path.resolve())
    assert not recent[0].pinned

    mgr.clear()

