"""Terminal tool: execute commands on Windows (PowerShell/CMD) with UTF-8."""

from __future__ import annotations

import asyncio
import shutil
import sys
from typing import Any

from axiom.core.logging import get_logger
from axiom.core.types import ToolResult
from axiom.permissions.policy import SecurityPolicy
from axiom.permissions.rules import is_blocked_command
from axiom.tools.registry import ToolContext

logger = get_logger("terminal")

_MAX_OUTPUT = 30000


def resolve_shell(shell: str | None = None) -> tuple[str, str]:
    """Return (program, flag) for running commands. Windows-first."""
    shell = shell or "powershell"
    if sys.platform == "win32":
        if shell == "cmd":
            return "cmd.exe", "/c"
        pwsh = shutil.which("pwsh")
        ps = pwsh or shutil.which("powershell")
        if ps:
            return ps, "-NoProfile -NonInteractive -Command"
    return "/bin/sh", "-c"


def _truncate(text: str, limit: int = _MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} chars omitted]"


async def run_shell(
    command: str,
    workspace: str,
    timeout: float = 60.0,
    shell: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a shell command; return (exit_code, stdout, stderr)."""
    if is_blocked_command(command):
        return 126, "", "Error: command blocked by security policy."
    program, flag = resolve_shell(shell)
    if program.endswith(("powershell.exe", "pwsh.exe")):
        argv = [program, "-NoProfile", "-NonInteractive", "-Command", command]
    elif program == "cmd.exe":
        argv = [program, "/c", command]
    else:
        argv = [program, "-c", command]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except OSError as exc:
        return 127, "", f"Error: cannot start process: {exc}"
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        return 124, "", f"Error: command timed out after {timeout}s."
    stdout = out.decode("utf-8", "replace")
    stderr = err.decode("utf-8", "replace")
    return proc.returncode or 0, stdout, stderr


async def execute_command(
    command: str, timeout: float = 60.0, _context: ToolContext = None  # type: ignore[assignment]
) -> ToolResult:
    """Execute a shell command in the workspace and return combined output."""
    ctx = _context
    policy = SecurityPolicy(security_mode=ctx.permission_manager.security_mode)
    permission, reason = policy.command_permission(command)
    if reason:
        return ToolResult(
            tool_call_id="", name="execute_command",
            content=f"Error: blocked: dangerous command pattern ({reason.strip(': ')})",
            is_error=True,
        )
    code, out, err = await run_shell(
        command, ctx.workspace, timeout=timeout,
        shell=(ctx.config or {}).get("shell"),
    )
    parts = [f"exit_code: {code}"]
    if out.strip():
        parts.append(f"stdout:\n{_truncate(out)}")
    if err.strip():
        parts.append(f"stderr:\n{_truncate(err)}")
    return ToolResult(
        tool_call_id="",
        name="execute_command",
        content="\n".join(parts),
        is_error=code != 0,
        metadata={"exit_code": code},
    )
