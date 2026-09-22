"""Permission Manager — centralised permission decision engine.

Supports three modes:
- ask: Every tool execution requires user confirmation.
- auto_approve_safe: Safe (ALWAYS) tools run automatically, ASK tools require confirmation.
- auto_approve_all: All tools execute without confirmation.

The setting persists between launches via the config file.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from axiom.core.config import Config
from axiom.core.logging import get_logger
from axiom.core.tools.base import ToolPermission

_LOG = get_logger("permissions")


class PermissionMode(str, Enum):
    """Global permission mode."""
    ASK = "ask"
    AUTO_APPROVE_SAFE = "auto_approve_safe"
    AUTO_APPROVE_ALL = "auto_approve_all"


class PermissionManager:
    """Centralised permission decision engine.

    The TUI connects a callback (``request_callback``) that shows the user a
    modal dialog when ``ASK`` tools need approval. The callback is an async
    callable that receives ``(tool_name, tool_args)`` and returns ``True``
    (approved) or ``False`` (denied).
    """

    def __init__(
        self,
        config: Config | None = None,
        *,
        request_callback: Callable[[str, dict[str, Any]], bool] | None = None,
    ) -> None:
        self._config = config or Config.load()
        self._request_callback = request_callback
        #: Cache: tool name -> last user decision (for the current session).
        self._session_cache: dict[str, bool] = {}

    # ------------------------------------------------------------------ properties

    @property
    def mode(self) -> PermissionMode:
        raw = getattr(self._config, "permission_mode", PermissionMode.AUTO_APPROVE_SAFE.value)
        try:
            return PermissionMode(raw)
        except ValueError:
            return PermissionMode.AUTO_APPROVE_SAFE

    @mode.setter
    def mode(self, value: PermissionMode) -> None:
        self._config.permission_mode = value.value  # type: ignore[attr-defined]
        self._config.save()

    @property
    def modes_text(self) -> dict[PermissionMode, str]:
        return {
            PermissionMode.ASK: "Ask every time",
            PermissionMode.AUTO_APPROVE_SAFE: "Auto-approve safe actions",
            PermissionMode.AUTO_APPROVE_ALL: "Auto-approve everything",
        }

    # ------------------------------------------------------------------ decision

    def request_callback(self, callback: Callable[[str, dict[str, Any]], bool]) -> None:
        """Connect a UI callback for user approval dialogs."""
        self._request_callback = callback

    async def decide(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | None,
        tool_permission: ToolPermission,
    ) -> bool:
        """Check whether a tool execution is allowed.

        Returns:
            True if execution may proceed, False otherwise.
        """
        _LOG.debug("Permission check: %s (perm=%s, mode=%s)", tool_name, tool_permission.value, self.mode.value)

        # NEVER permission is always blocked regardless of mode.
        if tool_permission == ToolPermission.NEVER:
            return False

        if self.mode == PermissionMode.AUTO_APPROVE_ALL:
            return True

        if self.mode == PermissionMode.AUTO_APPROVE_SAFE:
            if tool_permission == ToolPermission.ALWAYS:
                return True
            # ASK tools need user approval.
            return await self._ask_user(tool_name, tool_args or {})

        # ASK mode — everything needs approval.
        return await self._ask_user(tool_name, tool_args or {})

    async def _ask_user(self, tool_name: str, tool_args: dict[str, Any]) -> bool:
        """Show a permission request to the user, or use cache."""
        cache_key = f"{tool_name}:{hash(frozenset(tool_args.items())) % 10000}"
        if cache_key in self._session_cache:
            return self._session_cache[cache_key]

        if self._request_callback is not None:
            approved = self._request_callback(tool_name, tool_args)
            if approved:
                self._session_cache[cache_key] = True
                _LOG.info("Permission granted: %s %s", tool_name, tool_args)
            else:
                _LOG.info("Permission denied: %s %s", tool_name, tool_args)
            return approved

        # No callback available — deny by default (safe fallback).
        _LOG.warning("No permission callback registered; denying tool: %s", tool_name)
        return False

    def clear_cache(self) -> None:
        """Clear the session permission cache."""
        self._session_cache.clear()
