"""Tests for the user-initiated git write helpers (stage/unstage/commit/diff)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from axiom.core.tools.git_tools import (
    git_commit,
    git_diff_file,
    git_stage,
    git_switch,
    git_unstage,
)


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-m", "initial")
    return tmp_path


def test_stage_and_commit(repo: Path):
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    git_stage(repo, ["a.txt"])
    assert "a.txt" in git(repo, "diff", "--cached", "--name-only")
    out = git_commit(repo, "change a")
    assert out
    assert "two" in (repo / "a.txt").read_text(encoding="utf-8")
    assert "change a" in git(repo, "log", "-1", "--pretty=%s")


def test_unstage(repo: Path):
    (repo / "a.txt").write_text("three\n", encoding="utf-8")
    git_stage(repo, ["a.txt"])
    git_unstage(repo, ["a.txt"])
    assert not git(repo, "diff", "--cached", "--name-only").strip()


def test_empty_commit_message_rejected(repo: Path):
    with pytest.raises(ValueError, match="empty"):
        git_commit(repo, "   ")


def test_path_escape_rejected(repo: Path):
    with pytest.raises(ValueError, match="escapes"):
        git_stage(repo, ["../outside.txt"])


def test_diff_file_shows_change(repo: Path):
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    diff = git_diff_file(repo, "a.txt")
    assert "+changed" in diff
    assert "-one" in diff


def test_diff_untracked_file_synthesized(repo: Path):
    (repo / "fresh.txt").write_text("brand new\n", encoding="utf-8")
    diff = git_diff_file(repo, "fresh.txt")
    assert "+++ b/fresh.txt" in diff
    assert "+brand new" in diff


def test_switch_branch(repo: Path):
    initial = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    git(repo, "checkout", "-b", "feature")
    git(repo, "checkout", initial)
    out = git_switch(repo, "feature")
    assert out
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "feature"


def test_switch_rejects_bad_branch_names(repo: Path):
    with pytest.raises(ValueError, match=r"[Ee]mpty"):
        git_switch(repo, "   ")
    with pytest.raises(ValueError, match="Invalid"):
        git_switch(repo, "--force")


def test_switch_unknown_branch_reports_git_error(repo: Path):
    with pytest.raises(ValueError):
        git_switch(repo, "no-such-branch")
