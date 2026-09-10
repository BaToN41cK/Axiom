"""Permission system.

status: ALLOW / ASK / DENY per named permission; supports session cache,
"always" approval persistence and a UI callback for ASK prompts.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from axiom.config.defaults import DEFAULT_PERMISSIONS, SECURITY_MODE_PRESETS
from axiom.core.types import PermissionState
from axiom.core.logging import get_logger

logger = get_logger("permissions")


@dataclass
class PermissionRequest:
    """A request to perform an action guarded by a permission."""

    permission: str
    action: str = ""
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        if self.detail:
            return self.detail
        return self.action or self.permission


@dataclass
class PermissionResponse:
    """User's decision for a permission request."""

    allowed: bool
    always: bool = False
    remember: bool = False  # remember for the current session


AskCallback = Callable[[PermissionRequest], Awaitable[PermissionResponse]]


class PermissionManager:
    """Central permission engine."""

    def __init__(
        self,
        config: dict[str, str] | None = None,
        security_mode: str = "NORMAL",
        always_file: Path | None = None,
    ) -> None:
        self._config: dict[str, str] = dict(DEFAULT_PERMISSIONS)
        self._config.update(config or {})
        self._security_mode = security_mode
        self._callback: AskCallback | None = None
        self._session_cache: dict[str, PermissionState] = {}
        self._always_file = always_file or (Path.home() / ".axiom" / "permissions.json")
        self._always: dict[str, str] = self._load_always()

    # -- setup -----------------------------------------------------------
    def set_callback(self, callback: AskCallback) -> None:
        self._callback = callback

    def set_security_mode(self, mode: str) -> None:
        """Apply a security mode preset (SAFE/NORMAL/AUTONOMOUS)."""
        mode = mode.upper()
        if mode not in SECURITY_MODE_PRESETS:
            return
        self._security_mode = mode
        preset = SECURITY_MODE_PRESETS[mode]
        for name, state in preset.items():
            # never override an explicit "always" user approval
            if self._always.get(name) != "allow":
                self._config[name] = state
        self._session_cache.clear()
        logger.info("Security mode set to %s", mode)

    @property
    def security_mode(self) -> str:
        return self._security_mode

    def set_permission(self, name: str, state: PermissionState) -> None:
        self._config[name] = state.value
        self._session_cache.pop(name, None)

    def get_permission_state(self, name: str) -> PermissionState:
        if name in self._session_cache:
            return self._session_cache[name]
        raw = self._config.get(name)
        if raw is None:
            return PermissionState.ASK
        try:
            return PermissionState(raw.lower())
        except ValueError:
            return PermissionState.ASK

    def is_allowed(self, name: str) -> bool | None:
        """True/False if statically decided, None when ASK."""
        return {PermissionState.ALLOW: True, PermissionState.DENY: False}.get(
            self.get_permission_state(name)
        )

    def list_permissions(self) -> dict[str, str]:
        merged = dict(self._config)
        return merged

    # -- check -----------------------------------------------------------
    async def check(self, request: PermissionRequest) -> PermissionResponse:
        state = self.get_permission_state(request.permission)
        if state is PermissionState.ALLOW:
            return PermissionResponse(allowed=True)
        if state is PermissionState.DENY:
            return PermissionResponse(allowed=False)
        # ASK
        if self._callback is None:
            logger.info("Auto-denied (no callback): %s", request.permission)
            return PermissionResponse(allowed=False)
        response = await self._callback(request)
        if response.always:
            self._config[request.permission] = (
                PermissionState.ALLOW.value if response.allowed else PermissionState.DENY.value
            )
            self._save_always(request.permission, response.allowed)
        elif response.remember:
            self._session_cache[request.permission] = (
                PermissionState.ALLOW if response.allowed else PermissionState.DENY
            )
        return response

    # -- "always" persistence --------------------------------------------
    def _load_always(self) -> dict[str, str]:
        try:
            if self._always_file.is_file():
                data = json.loads(self._always_file.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _save_always(self, name: str, allowed: bool) -> None:
        self._always[name] = "allow" if allowed else "deny"
        try:
            self._always_file.parent.mkdir(parents=True, exist_ok=True)
            self._always_file.write_text(
                json.dumps(self._always, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Failed to save permissions: %s", exc)
