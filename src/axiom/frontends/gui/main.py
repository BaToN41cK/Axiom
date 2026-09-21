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

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

_EXIT_OK = 0
_EXIT_ERROR = 1

#: Binary names Tauri produces for the current platform.
_EXE_CANDIDATES = ("axiom-desktop.exe", "AXIOM.exe", "axiom.exe", "axiom-desktop", "axiom", "AXIOM")

#: Build profiles in launch preference order: a release build embeds the
#: frontend, a debug build has none and needs the Vite dev server.
_PROFILE_ORDER = ("release", "debug")

#: Used when tauri.conf.json cannot be read.
_FALLBACK_DEV_URL = "http://localhost:1420"

#: How long to wait for the dev server to answer, and how often to poll it.
_DEV_SERVER_WAIT = 30.0
_DEV_SERVER_POLL = 0.15

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


def _dev_url(desktop: Path) -> str:
    """Frontend dev URL of the desktop app (``build.devUrl`` in tauri.conf.json)."""
    url: object = None
    try:
        conf = json.loads((desktop / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        build = conf.get("build", {}) if isinstance(conf, dict) else {}
        url = build.get("devUrl") if isinstance(build, dict) else None
    except (OSError, ValueError):
        url = None
    if isinstance(url, str) and url.strip():
        return url.strip()
    return _FALLBACK_DEV_URL


def _dev_server_port(dev_url: str) -> int | None:
    """TCP port the dev server serves ``dev_url`` on (``None`` if unparsable)."""
    try:
        parsed = urlsplit(dev_url)
        return parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None


def _port_is_open(port: int, timeout: float = 0.25) -> bool:
    """True when something accepts TCP connections on localhost:port.

    Both address families are probed on purpose: Vite resolves ``localhost``
    to a single address (IPv6 ``::1`` on Windows), so an IPv4-only check
    reports a running dev server as dead.
    """
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                if sock.connect_ex((host, port)) == 0:
                    return True
        except OSError:  # address family unavailable on this host
            continue
    return False


def _dev_server_answers(dev_url: str, timeout: float = 0.6) -> bool:
    """True when the dev server really serves HTTP at ``dev_url``.

    A bare TCP probe is not enough — the port may be held by an unrelated
    process. An explicitly empty ProxyHandler keeps a system proxy away from
    localhost: a proxy that intercepts local traffic answers 503 and would
    otherwise make a perfectly healthy dev server look dead.
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(dev_url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except (OSError, ValueError):
        return False


def _is_dev_build(exe: Path) -> bool:
    """True for a Tauri debug build, which carries no frontend of its own.

    ``tauri dev`` compiles the shell without embedded assets: the window loads
    ``build.devUrl``. Such an exe is therefore useless — and renders
    ``ERR_CONNECTION_REFUSED`` — unless the Vite dev server is up.
    """
    return exe.parent.name == "debug"


def _desktop_of(exe: Path) -> Path | None:
    """``desktop/`` directory an exe belongs to (…/src-tauri/target/<profile>/)."""
    parents = exe.parents
    if len(parents) < 4 or not (parents[3] / "package.json").exists():
        return None
    return parents[3]


def _newest_web_source() -> float:
    """Newest mtime of the web frontend sources (``desktop/src``)."""
    newest = 0.0
    for desktop in _desktop_dirs():
        src_dir = desktop / "src"
        # Only the web frontend counts (desktop/src); a bare repo root also
        # has src/ (the Python package) but it is not part of the exe.
        if src_dir.exists() and (desktop / "src-tauri").exists():
            mtimes = (p.stat().st_mtime for p in src_dir.rglob("*") if p.is_file())
            newest = max(newest, max(mtimes, default=0.0))
    return newest


def _built_exe(profile: str) -> Path | None:
    """Newest built exe of one profile across all known desktop directories."""
    best: Path | None = None
    for desktop in _desktop_dirs():
        target = desktop / "src-tauri" / "target" / profile
        for exe in _EXE_CANDIDATES:
            candidate = target / exe
            if candidate.is_file() and (best is None or candidate.stat().st_mtime > best.stat().st_mtime):
                best = candidate
    return best


def _find_built_exe_any(profile: str | None = None) -> Path | None:
    """Newest built exe regardless of source staleness (fallback path)."""
    profiles = (profile,) if profile else _PROFILE_ORDER
    best: Path | None = None
    for name in profiles:
        candidate = _built_exe(name)
        if candidate is not None and (best is None or candidate.stat().st_mtime > best.stat().st_mtime):
            best = candidate
    return best


def _find_built_exe() -> Path | None:
    """Built shell worth launching, or ``None`` when the dev shell is better.

    A release build embeds the frontend, so it is used only while it is not
    older than the web sources (otherwise the UI would be stale). A debug
    build always takes its UI from the dev server — web sources never make it
    stale — but it only runs once that server is started (see
    :func:`_launch_exe`).
    """
    newest_source = _newest_web_source()
    release = _built_exe("release")
    if release is not None and (not newest_source or release.stat().st_mtime >= newest_source):
        return release
    return _built_exe("debug")


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
        install = subprocess.run([npm_cmd, "install"], cwd=desktop, stdin=subprocess.DEVNULL)
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
        subprocess.Popen([str(exe)], stdin=subprocess.DEVNULL, creationflags=_DETACHED, close_fds=True)
    else:
        subprocess.Popen([str(exe)], stdin=subprocess.DEVNULL, start_new_session=True)


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
