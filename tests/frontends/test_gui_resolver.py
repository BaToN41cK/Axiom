"""Pure path resolver of the GUI launcher (frontends/gui/main.py)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

import axiom.frontends.gui.main as gui

# --------------------------------------------------------------- _desktop_dirs


def test_desktop_dirs_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_DESKTOP_ROOT", str(tmp_path))
    (tmp_path / "desktop").mkdir()
    dirs = gui._desktop_dirs()
    assert dirs[0] == tmp_path / "desktop"
    # No duplicates even when cwd equals the candidate.
    assert len(dirs) == len(set(dirs))


def test_desktop_dirs_falls_back_to_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AXIOM_DESKTOP_ROOT", raising=False)
    assert (gui._project_root() / "desktop") in gui._desktop_dirs()


# ------------------------------------------------------------- exe resolution


def _make_exe(root: Path, name: str = "axiom-desktop.exe") -> Path:
    exe = root / "src-tauri" / "target" / "release" / name
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    return exe


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the resolver away from the real repository desktop/."""
    monkeypatch.setenv("AXIOM_DESKTOP_ROOT", str(tmp_path))
    monkeypatch.setattr(gui, "_project_root", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)


def test_finds_fresh_exe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate(tmp_path, monkeypatch)
    desktop = tmp_path / "desktop"
    (desktop / "src").mkdir(parents=True)
    (desktop / "src-tauri").mkdir(parents=True)
    (desktop / "src" / "index.tsx").write_text("x", encoding="utf-8")
    exe = _make_exe(desktop)
    os.utime(exe, (time.time() + 5, time.time() + 5))  # newer than any source
    assert gui._find_built_exe() == exe


def test_stale_exe_is_not_used_when_sources_are_newer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(tmp_path, monkeypatch)
    desktop = tmp_path / "desktop"
    (desktop / "src").mkdir(parents=True)
    (desktop / "src-tauri").mkdir(parents=True)
    exe = _make_exe(desktop)
    os.utime(exe, (1, 1))  # ancient build
    (desktop / "src" / "index.tsx").write_text("x", encoding="utf-8")  # newer source
    assert gui._find_built_exe() is None


def test_fallback_finds_even_stale_exe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate(tmp_path, monkeypatch)
    desktop = tmp_path / "desktop"
    (desktop / "src").mkdir(parents=True)
    (desktop / "src-tauri").mkdir(parents=True)
    exe = _make_exe(desktop)
    os.utime(exe, (1, 1))
    (desktop / "src" / "index.tsx").write_text("x", encoding="utf-8")
    assert gui._find_built_exe_any() == exe


def test_no_exe_anywhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    assert gui._find_built_exe() is None
    assert gui._find_built_exe_any() is None


def test_windows_detached_flags_defined() -> None:
    if sys.platform == "win32":
        assert gui._DETACHED != 0
    else:
        assert gui._DETACHED == 0
