"""Shared pytest fixtures for AXIOM tests (installed package, no UI)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from axiom.core.config import Config

# The project uses src/ layout with editable install; make doubly sure
# ``import axiom`` resolves to the working tree under test.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def test_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Isolated Config pointing AXIOM_HOME at a tmp dir (no real ~/.axiom writes)."""
    home = tmp_path / "axiom-home"
    monkeypatch.setenv("AXIOM_HOME", str(home))
    cfg = Config()
    cfg.model = "test-model:latest"
    return cfg
