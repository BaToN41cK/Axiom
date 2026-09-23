"""Sandbox / Permission System 2.0: уровни + политики (п.13).

Уровни: READ / WRITE / EXECUTE / NETWORK / GIT / DELETE.
Политики: ask / auto / deny. Решение по паре (уровень, политика).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SandboxLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    GIT = "git"
    DELETE = "delete"


class SandboxPolicy(str, Enum):
    ASK = "ask"
    AUTO = "auto"
    DENY = "deny"


TOOL_LEVELS: dict[str, SandboxLevel] = {
    "web_search": SandboxLevel.NETWORK, "fetch_url": SandboxLevel.NETWORK,
    "list_files": SandboxLevel.READ, "read_file": SandboxLevel.READ,
    "search_text": SandboxLevel.READ, "search_files": SandboxLevel.READ,
    "inspect_project": SandboxLevel.READ,
    "git_status": SandboxLevel.GIT, "git_diff": SandboxLevel.GIT,
    "git_log": SandboxLevel.GIT, "git_branch": SandboxLevel.GIT,
    "write_file": SandboxLevel.WRITE, "edit_file": SandboxLevel.WRITE,
    "create_directory": SandboxLevel.WRITE, "copy_file": SandboxLevel.WRITE,
    "move_file": SandboxLevel.WRITE,
    "delete_file": SandboxLevel.DELETE,
    "run_command": SandboxLevel.EXECUTE,
}


def level_of(tool_name: str) -> SandboxLevel:
    return TOOL_LEVELS.get(tool_name, SandboxLevel.EXECUTE)


@dataclass
class Sandbox:
    """Политики по умолчанию: read=auto, write/execute=auto, delete/network=ask."""

    policies: dict[SandboxLevel, SandboxPolicy] = field(default_factory=lambda: {
        SandboxLevel.READ: SandboxPolicy.AUTO,
        SandboxLevel.WRITE: SandboxPolicy.AUTO,
        SandboxLevel.EXECUTE: SandboxPolicy.AUTO,
        SandboxLevel.NETWORK: SandboxPolicy.AUTO,
        SandboxLevel.GIT: SandboxPolicy.AUTO,
        SandboxLevel.DELETE: SandboxPolicy.ASK,
    })
    ask_callback: object = None

    def set_policy(self, level: SandboxLevel, policy: SandboxPolicy) -> None:
        self.policies[level] = policy

    def decide(self, tool_name: str) -> str:
        """Возвращает 'auto' | 'ask' | 'deny'."""
        level = level_of(tool_name)
        policy = self.policies.get(level, SandboxPolicy.ASK)
        return policy.value

    def allows(self, tool_name: str) -> bool:
        return self.decide(tool_name) != SandboxPolicy.DENY.value
