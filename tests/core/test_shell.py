"""Interactive shell session tests (``axiom.core.tools.shell``)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from axiom.core.tools.shell import ShellSession, default_shell_argv


def wait_for(session: ShellSession, needle: str, timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = session.read()
        if needle in out:
            return out
        time.sleep(0.05)
    return session.read()


def test_shell_session_roundtrip(tmp_path: Path):
    """Write a line, read real output from the persistent process."""
    # Use Python as the shell so the test is portable and deterministic.
    os.environ["AXIOM_SHELL"] = f"{sys.executable} -i"
    session = ShellSession(tmp_path)
    try:
        session.start()
        assert session.running
        assert session.write("print(2 + 2)")
        out = wait_for(session, "4")
        assert "4" in out
        # Persistence: the second command still hits the same live process.
        assert session.write("print('again')")
        assert "again" in wait_for(session, "again")
    finally:
        session.stop()
        del os.environ["AXIOM_SHELL"]
    assert not session.running


def test_write_to_dead_session_returns_false(tmp_path: Path):
    session = ShellSession(tmp_path)
    assert session.write("anything") is False


def test_default_argv_is_non_empty():
    argv = default_shell_argv()
    assert argv and isinstance(argv[0], str)
