"""Scenario §29 — switching projects keeps AI/Explorer/Terminal on one workspace."""

from __future__ import annotations

import asyncio
from pathlib import Path

from axiom.core.chat import ChatSession
from axiom.core.config import Config


def _make(root: Path, kind: str) -> Path:
    proj = root / kind
    (proj / "src").mkdir(parents=True, exist_ok=True)
    if kind == "ProjectA":
        (proj / "pyproject.toml").write_text("[project]\nname='a'\n", encoding="utf-8")
        (proj / "src" / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    else:
        (proj / "package.json").write_text("{}\n", encoding="utf-8")
        (proj / "src" / "app.js").write_text("const x = 1;\n", encoding="utf-8")
    return proj


async def _scenario(tmp_path: Path) -> None:
    session = ChatSession(config=Config(save_history=False, workspace_tools_enabled=True))
    proj_a = _make(tmp_path, "ProjectA")
    proj_b = _make(tmp_path, "ProjectB")

    # 2-4. Open A, AI reads real files.
    info_a = session.set_workspace(str(proj_a))
    assert info_a.kind == "Python"
    res = await session.tools.execute("read_file", {"path": "src/main.py"})
    assert res.ok and "VALUE = 1" in res.content

    # 5-6. Terminal runs inside A.
    out = await session.run_terminal("git status", confirmed=False)
    assert out["cwd"] == str(proj_a.resolve())

    # 7-11. Switch to B: everything follows, A is untouched.
    info_b = session.set_workspace(str(proj_b))
    assert info_b.kind == "Node / JS"
    assert session.workspace_root == proj_b.resolve()
    assert session.terminal is not None and session.terminal.root == proj_b.resolve()
    res_b = await session.tools.execute("read_file", {"path": "src/app.js"})
    assert res_b.ok and "const x" in res_b.content
    missing = await session.tools.execute("read_file", {"path": "src/main.py"})
    assert not missing.ok  # A's file is NOT visible from B
    out_b = await session.run_terminal("git status", confirmed=False)
    assert out_b["cwd"] == str(proj_b.resolve())

    # 12-13. Back to A: state restored (same root, same history dir).
    session.set_workspace(str(proj_a))
    assert session.workspace_root == proj_a.resolve()
    back = await session.tools.execute("read_file", {"path": "src/main.py"})
    assert back.ok


def test_project_switching_scenario(tmp_path: Path) -> None:
    asyncio.run(_scenario(tmp_path))



async def test_chat_drops_missing_configured_workspace(tmp_path, monkeypatch):
    from axiom.core.chat import ChatSession
    from axiom.core.config import Config
    from axiom.core.history import HistoryStore

    monkeypatch.chdir(tmp_path)
    stale = tmp_path / "gone"
    cfg = Config(save_history=False, workspace_tools_enabled=True, workspace_root=str(stale))
    session = ChatSession(config=cfg, history_store=HistoryStore(directory=tmp_path / "history"))
    assert session.config.workspace_root is None
    assert session.workspace_root == tmp_path.resolve()
    result = await session.tools.execute("read_file", {"path": "missing.py"})
    assert not result.ok
    assert "missing.py" in (result.error or "")
