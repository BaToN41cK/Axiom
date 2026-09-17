"""AXIOM GUI frontend launcher (``axiom --gui``).

The desktop GUI itself is a Tauri app that lives in ``desktop/`` (React
frontend + Rust shell that spawns the real Python core as a JSONL stdio
bridge). This module only *launches* it:

    1. a pre-built binary (``desktop/src-tauri/target/release/AXIOM.exe``
       or the debug build) — preferred, starts instantly;
    2. ``npm run tauri dev`` — compiles on the fly (requires Node.js and
       the Rust toolchain);
    3. a helpful error explaining what to install otherwise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_EXIT_OK = 0
_EXIT_ERROR = 1

#: Binary names Tauri produces for the current platform.
_EXE_CANDIDATES = ("axiom-desktop.exe", "AXIOM.exe", "axiom.exe", "axiom-desktop", "axiom", "AXIOM")

_IS_WINDOWS = sys.platform == "win32"

#: Detached launch flags: the GUI must survive the terminal being closed.
if _IS_WINDOWS:
    _DETACHED = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
else:
    _DETACHED = 0


def _project_root() -> Path:
    """Repo root: this file is ``<root>/src/axiom/frontends/gui/main.py``."""
    return Path(__file__).resolve().parents[4]


def _desktop_dirs() -> list[Path]:
    """Where the desktop app may live (first existing wins for the search)."""
    candidates: list[Path] = []
    env_root = os.environ.get("AXIOM_DESKTOP_ROOT")
    if env_root:
        candidates.append(Path(env_root) / "desktop")
    candidates.append(_project_root() / "desktop")
    candidates.append(Path.cwd() / "desktop")
    candidates.append(Path.cwd())  # already inside desktop/
    unique: list[Path] = []
    for d in candidates:
        if d.exists() and d not in unique:
            unique.append(d)
    return unique


def _find_built_exe_any() -> Path | None:
    """Newest built exe regardless of source staleness (fallback path)."""
    best: Path | None = None
    for desktop in _desktop_dirs():
        for profile in ("release", "debug"):
            target = desktop / "src-tauri" / "target" / profile
            for exe in _EXE_CANDIDATES:
                candidate = target / exe
                if candidate.is_file() and (best is None or candidate.stat().st_mtime > best.stat().st_mtime):
                    best = candidate
    return best


def _find_built_exe() -> Path | None:
    """Newest built exe, but only if it is not older than the web sources.

    The frontend is compiled INTO the exe at build time; if sources changed
    after the last build, prefer the dev shell so the UI is never stale.
    """
    newest_source = 0.0
    for desktop in _desktop_dirs():
        src_dir = desktop / "src"
        # Only the web frontend counts (desktop/src); a bare repo root also
        # has src/ (the Python package) but it is not part of the exe.
        if src_dir.exists() and (desktop / "src-tauri").exists():
            mtimes = (p.stat().st_mtime for p in src_dir.rglob("*") if p.is_file())
            newest_source = max(newest_source, max(mtimes, default=0.0))
    best: Path | None = None
    for desktop in _desktop_dirs():
        for profile in ("release", "debug"):
            target = desktop / "src-tauri" / "target" / profile
            for exe in _EXE_CANDIDATES:
                candidate = target / exe
                if candidate.is_file() and (best is None or candidate.stat().st_mtime > best.stat().st_mtime):
                    best = candidate
    if best is None:
        return None
    if newest_source and best.stat().st_mtime < newest_source:
        return None  # stale build → dev shell rebuilds with current sources
    return best


def _run_dev(desktop: Path) -> int:
    """Start the Tauri dev shell (Vite + Rust build) fully detached.

    No console window is shown: the build runs in a detached process with
    output redirected to a log file, so closing the caller's terminal can
    never kill the build or the GUI.
    """
    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_cmd is None:
        print(
            "✕ Node.js (npm) не найден в PATH.\n"
            "  Установите Node.js LTS: https://nodejs.org/download/",
            file=sys.stderr,
        )
        return _EXIT_ERROR
    if shutil.which("cargo") is None and shutil.which("cargo.exe") is None:
        print(
            "✕ Rust toolchain (cargo) не найден в PATH — Tauri собирает "
            "нативное окно на Rust.\n"
            "  Установите rustup: https://rustup.ru/  (Windows: дополнительно "
            "нужны MSVC Build Tools — rustup предложит их сам).\n"
            "  После установки откройте НОВЫЙ терминал и повторите: axiom --gui",
            file=sys.stderr,
        )
        return _EXIT_ERROR
    if not (desktop / "node_modules").exists():
        print(f"Устанавливаю зависимости десктоп-приложения ({desktop})…", file=sys.stderr)
        install = subprocess.run([npm_cmd, "install"], cwd=desktop)
        if install.returncode != 0:
            return _EXIT_ERROR
    log_path = desktop / "tauri_dev.log"
    if _IS_WINDOWS:
        # Fully detached, no window at all; build output goes to the log.
        log = open(log_path, "ab")  # noqa: SIM115 - stays open for the child lifetime
        subprocess.Popen(
            [npm_cmd, "run", "tauri", "dev"],
            cwd=desktop,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=_DETACHED,
        )
        log.close()
    else:
        log = open(log_path, "ab")  # noqa: SIM115 - stays open for the child lifetime
        subprocess.Popen(
            [npm_cmd, "run", "tauri", "dev"],
            cwd=desktop,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        log.close()
    print(
        "AXIOM Desktop собирается и запустится в отдельном процессе — "
        "первая сборка Rust может занять несколько минут.\n"
        "Это окно терминала можно закрыть в любой момент: GUI от него не "
        "зависит.\n"
        f"Лог сборки: {log_path}",
        file=sys.stderr,
    )
    return _EXIT_OK


def _spawn_detached(exe: Path) -> None:
    """Start the exe detached so the terminal can be closed freely."""
    if _IS_WINDOWS:
        subprocess.Popen([str(exe)], creationflags=_DETACHED, close_fds=True)
    else:
        subprocess.Popen([str(exe)], start_new_session=True)


def main() -> int:
    """Entry point for ``axiom --gui``. Never raises."""
    exe = _find_built_exe()
    if exe is not None:
        try:
            # Detached: the GUI keeps running after the terminal is closed,
            # and no inherited pipe pins this process to the console.
            _spawn_detached(exe)
            return _EXIT_OK
        except FileNotFoundError:
            pass
    for desktop in _desktop_dirs():
        if (desktop / "package.json").exists() and (desktop / "src-tauri").exists():
            dev = _run_dev(desktop)
            if dev == _EXIT_OK and _IS_WINDOWS:
                return _EXIT_OK  # detached build already started
            if dev == _EXIT_ERROR:
                # Toolchain missing → try even a stale exe rather than nothing.
                exe = _find_built_exe_any()
                if exe is not None:
                    try:
                        _spawn_detached(exe)
                        return _EXIT_OK
                    except FileNotFoundError:
                        pass
            return dev
    print(
        "✕ Десктопное приложение AXIOM не найдено.\n"
        "  GUI живёт в папке desktop/ репозитория (Tauri + React).\n"
        "  Варианты запуска:\n"
        "    cd desktop && npm install && npm run tauri dev   # сборка на лету\n"
        "    cd desktop && npm run tauri build                # релизный exe",
        file=sys.stderr,
    )
    return _EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
