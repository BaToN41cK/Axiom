"""Tests for PermissionManager (axiom.core.permissions)."""

from __future__ import annotations

from typing import Any

import pytest

from axiom.core.config import Config
from axiom.core.permissions import PermissionManager, PermissionMode
from axiom.core.tools.base import ToolPermission


async def test_default_mode():
    # Use a fresh Config() to avoid reading a stale config file from disk.
    mgr = PermissionManager(config=Config())
    assert mgr.mode == PermissionMode.AUTO_APPROVE_SAFE


async def test_set_mode():
    mgr = PermissionManager()
    mgr.mode = PermissionMode.ASK
    assert mgr.mode == PermissionMode.ASK


async def test_auto_approve_all_allows_everything():
    mgr = PermissionManager()
    mgr.mode = PermissionMode.AUTO_APPROVE_ALL
    assert await mgr.decide("run", {}, ToolPermission.ALWAYS) is True
    assert await mgr.decide("run", {}, ToolPermission.NEVER) is False


async def test_never_permission_blocked():
    mgr = PermissionManager()
    mgr.mode = PermissionMode.AUTO_APPROVE_ALL
    assert await mgr.decide("danger", {}, ToolPermission.NEVER) is False


async def test_ask_with_callback():
    accepted: list[tuple[str, dict[str, Any]]] = []

    def callback(name: str, args: dict[str, Any]) -> bool:
        accepted.append((name, args))
        return True

    mgr = PermissionManager(request_callback=callback)
    mgr.mode = PermissionMode.ASK
    result = await mgr.decide("web_search", {"q": "test"}, ToolPermission.ASK)
    assert result is True
    assert len(accepted) == 1
    assert accepted[0][0] == "web_search"


async def test_async_approval_callback_is_awaited():
    calls: list[str] = []

    async def callback(name: str, args: dict[str, Any]) -> bool:
        calls.append(name)
        return True

    mgr = PermissionManager(request_callback=callback)
    mgr.mode = PermissionMode.ASK
    assert await mgr.decide(
        "terminal", {"command": "git status", "options": ["--short"]}, ToolPermission.ASK
    ) is True
    assert calls == ["terminal"]


async def test_approval_cache_supports_nested_arguments():
    calls: list[dict[str, Any]] = []

    def callback(name: str, args: dict[str, Any]) -> bool:
        calls.append(args)
        return True

    mgr = PermissionManager(request_callback=callback)
    mgr.mode = PermissionMode.ASK
    arguments = {"command": "git status", "options": ["--short"], "env": {"A": "1"}}
    assert await mgr.decide("terminal", arguments, ToolPermission.ASK) is True
    assert await mgr.decide("terminal", arguments, ToolPermission.ASK) is True
    assert calls == [arguments]


async def test_ask_denies_when_callback_false():
    def callback(name: str, args: dict[str, Any]) -> bool:
        return False

    mgr = PermissionManager(request_callback=callback)
    mgr.mode = PermissionMode.ASK
    result = await mgr.decide("terminal", {"cmd": "rm -rf"}, ToolPermission.ASK)
    assert result is False


async def test_ask_no_callback_denies_by_default():
    mgr = PermissionManager()
    mgr.mode = PermissionMode.ASK
    result = await mgr.decide("web_search", {}, ToolPermission.ASK)
    assert result is False


async def test_auto_approve_safe_allows_always_tools():
    mgr = PermissionManager()
    mgr.mode = PermissionMode.AUTO_APPROVE_SAFE
    assert await mgr.decide("read", {"path": "/tmp"}, ToolPermission.ALWAYS) is True


async def test_auto_approve_safe_asks_for_ask_tools():
    accepted: list[str] = []

    def callback(name: str, args: dict[str, Any]) -> bool:
        accepted.append(name)
        return True

    mgr = PermissionManager(request_callback=callback)
    mgr.mode = PermissionMode.AUTO_APPROVE_SAFE
    await mgr.decide("web_search", {}, ToolPermission.ASK)
    assert len(accepted) == 1


async def test_cache_used():
    calls: list[str] = []

    def callback(name: str, args: dict[str, Any]) -> bool:
        calls.append(name)
        return True

    mgr = PermissionManager(request_callback=callback)
    mgr.mode = PermissionMode.ASK
    # Same tool+args → second call should use cache
    await mgr.decide("web_search", {"q": "same"}, ToolPermission.ASK)
    await mgr.decide("web_search", {"q": "same"}, ToolPermission.ASK)
    assert len(calls) == 1


async def test_clear_cache():
    calls: list[str] = []

    def callback(name: str, args: dict[str, Any]) -> bool:
        calls.append(name)
        return True

    mgr = PermissionManager(request_callback=callback)
    mgr.mode = PermissionMode.ASK
    await mgr.decide("web_search", {"q": "test"}, ToolPermission.ASK)
    mgr.clear_cache()
    await mgr.decide("web_search", {"q": "test"}, ToolPermission.ASK)
    assert len(calls) == 2


async def test_config_persistence(monkeypatch: pytest.MonkeyPatch, tmp_path: Any):
    home = tmp_path / "axiom-home"
    monkeypatch.setenv("AXIOM_HOME", str(home))
    Config().save()

    cfg = Config.load()
    cfg.permission_mode = PermissionMode.ASK.value
    cfg.save()

    mgr = PermissionManager(config=cfg)
    assert mgr.mode == PermissionMode.ASK
