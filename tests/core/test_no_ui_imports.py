"""axiom.core must stay UI-free (REAL FIRST: core renders nothing itself)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FORBIDDEN = ("textual", "rich", "PyQt", "PySide", "toga", "tkinter")


def test_core_modules_import_without_ui_packages(monkeypatch: pytest.MonkeyPatch):
    """Importing core modules in a clean interpreter must not pull UI libs."""
    for name in ("textual", "rich"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import axiom.core.agent
    import axiom.core.chat
    import axiom.core.ollama

    assert axiom.core.agent.Agent is not None
    assert axiom.core.chat.ChatSession is not None
    assert axiom.core.ollama.OllamaClient is not None

    for name in ("textual", "rich", "PyQt5", "PyQt6", "PySide6", "toga", "tkinter"):
        assert name not in sys.modules, f"axiom.core pulled UI package: {name}"


def test_core_source_has_no_ui_imports():
    """Static guard: no UI framework import may appear in src/axiom/core."""
    root = Path(__file__).resolve().parents[2] / "src" / "axiom" / "core"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")):
                    first = stripped.split()
                    target = first[1] if len(first) > 1 else ""
                    if target.split(".")[0] in (token,):
                        offenders.append(f"{path.name}: {stripped}")
    assert offenders == [], "UI imports found in axiom.core:\n" + "\n".join(offenders)


def test_core_importable_in_isolation(tmp_path: Path):
    """Fresh interpreter: core imports fine with UI packages made unimportable."""
    script = (
        "import sys\n"
        "class Blocker:\n"
        "    def find_module(self, name, path=None):\n"
        "        if name.split('.')[0] in "
        "('textual', 'rich', 'PyQt5', 'PyQt6', 'PySide6', 'toga', 'tkinter'):\n"
        "            return self\n"
        "        return None\n"
        "    def load_module(self, name):\n"
        "        raise ImportError('blocked: ' + name)\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "import axiom.core.chat, axiom.core.agent, axiom.core.ollama\n"
        "print('core-ok')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "core-ok" in proc.stdout
