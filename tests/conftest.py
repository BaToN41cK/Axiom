"""Test configuration for Axiom."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path_chdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Change to temp directory for test."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _setup_test_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[None, None, None]:
    """Set up test environment variables."""
    # Use temp directory for config
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("HOME", tmpdir)
        monkeypatch.setenv("USERPROFILE", tmpdir)
        monkeypatch.setenv("AXIOM_HOME", tmpdir)
        monkeypatch.delenv("AXIOM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        try:
            yield
        finally:
            from axiom.core.logging import close_logging

            close_logging()
