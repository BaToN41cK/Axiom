"""Security policy: combines security mode + rules to decide permission state."""

from __future__ import annotations

from axiom.permissions.rules import derive_permission_for_command, is_blocked_command


class SecurityPolicy:
    """High-level policy decisions on top of the permission manager."""

    def __init__(self, security_mode: str = "NORMAL") -> None:
        self.security_mode = security_mode

    def mode_state(self, permission: str) -> str | None:
        """State imposed purely by the security mode, or None for defaults."""
        return {
            "SAFE": {"terminal.execute": "ask", "filesystem.write": "ask"},
            "NORMAL": {"terminal.execute": "ask"},
            "AUTONOMOUS": {"terminal.execute": "allow"},
        }.get(self.security_mode, {}).get(permission)

    def command_permission(self, command: str) -> tuple[str, str]:
        """Return (permission_name, reason) for a shell command."""
        if is_blocked_command(command):
            return "terminal.execute", "BLOCKED: dangerous command pattern"
        return derive_permission_for_command(command), ""
