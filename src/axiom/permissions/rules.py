"""Permission rules: derived permissions for concrete actions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Rule:
    """A rule deriving a concrete permission from an action."""

    match: str  # substring match on the action/command
    permission: str


# Commands that are considered read-only for the terminal tool.
READ_ONLY_COMMANDS: tuple[str, ...] = (
    "ls", "dir", "type ", "cat", "head", "tail", "findstr", "grep", "echo",
    "python --version", "python -V", "pip list", "pytest --version",
    "git status", "git log", "git diff", "git branch", "git show",
    "node --version", "npm --version", "cargo --version", "go version",
    "where", "which", "tree", "pwd", "hostname", "whoami",
)

# Commands that must never run regardless of permissions.
BLOCKED_COMMAND_PATTERNS: tuple[str, ...] = (
    "rm -rf /", "rd /s /q c:\\", "format c:", "diskpart",
    "shutdown", "cipher /w", "vssadmin delete", "reg add hklm",
    "> /dev/sda", "dd if=", "mkfs",
)


def derive_permission_for_command(command: str) -> str:
    """Return 'terminal.execute:readonly' style hint for a command."""
    lowered = command.lower().strip()
    for ro in READ_ONLY_COMMANDS:
        if lowered.startswith(ro):
            return "terminal.execute.readonly"
    return "terminal.execute"


def is_blocked_command(command: str) -> bool:
    lowered = command.lower()
    return any(pattern in lowered for pattern in BLOCKED_COMMAND_PATTERNS)
