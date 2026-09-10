"""Tests for permission system."""

from __future__ import annotations

import pytest

from axiom.core.types import PermissionState
from axiom.permissions.manager import PermissionManager, PermissionRequest, PermissionResponse


class TestPermissionManager:
    """Tests for PermissionManager."""

    def test_default_state_is_ask(self) -> None:
        pm = PermissionManager(config={})
        assert pm.get_permission_state("unknown.permission") == PermissionState.ASK

    def test_allow_permission(self) -> None:
        pm = PermissionManager(config={"test.perm": "allow"})
        assert pm.get_permission_state("test.perm") == PermissionState.ALLOW

    def test_deny_permission(self) -> None:
        pm = PermissionManager(config={"test.perm": "deny"})
        assert pm.get_permission_state("test.perm") == PermissionState.DENY

    @pytest.mark.asyncio
    async def test_check_allow(self) -> None:
        pm = PermissionManager(config={"test.perm": "allow"})
        request = PermissionRequest(permission="test.perm", action="test action")
        response = await pm.check(request)
        assert response.allowed is True

    @pytest.mark.asyncio
    async def test_check_deny(self) -> None:
        pm = PermissionManager(config={"test.perm": "deny"})
        request = PermissionRequest(permission="test.perm", action="test action")
        response = await pm.check(request)
        assert response.allowed is False

    @pytest.mark.asyncio
    async def test_check_ask_with_callback_allow(self) -> None:
        pm = PermissionManager(config={"test.perm": "ask"})

        async def mock_callback(req: PermissionRequest) -> PermissionResponse:
            return PermissionResponse(allowed=True, always=False)

        pm.set_callback(mock_callback)

        request = PermissionRequest(permission="test.perm", action="test")
        response = await pm.check(request)
        assert response.allowed is True

    @pytest.mark.asyncio
    async def test_check_ask_with_callback_deny(self) -> None:
        pm = PermissionManager(config={"test.perm": "ask"})

        async def mock_callback(req: PermissionRequest) -> PermissionResponse:
            return PermissionResponse(allowed=False)

        pm.set_callback(mock_callback)

        request = PermissionRequest(permission="test.perm", action="test")
        response = await pm.check(request)
        assert response.allowed is False

    @pytest.mark.asyncio
    async def test_check_ask_no_callback_denies(self) -> None:
        pm = PermissionManager(config={"test.perm": "ask"})
        request = PermissionRequest(permission="test.perm", action="test")
        response = await pm.check(request)
        assert response.allowed is False

    def test_set_permission(self) -> None:
        pm = PermissionManager(config={})
        pm.set_permission("test.perm", PermissionState.ALLOW)
        assert pm.get_permission_state("test.perm") == PermissionState.ALLOW

    def test_is_allowed_with_cache(self) -> None:
        pm = PermissionManager(config={"test.perm": "allow"})
        assert pm.is_allowed("test.perm") is True

    def test_is_allowed_deny(self) -> None:
        pm = PermissionManager(config={"test.perm": "deny"})
        assert pm.is_allowed("test.perm") is False

    def test_is_allowed_ask_returns_none(self) -> None:
        pm = PermissionManager(config={"test.perm": "ask"})
        assert pm.is_allowed("test.perm") is None
