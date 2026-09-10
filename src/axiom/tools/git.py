"""Git tools (read ops allowed by default; write ops permission-gated)."""

from __future__ import annotations

import shutil

from axiom.core.types import ToolResult
from axiom.tools.terminal import run_shell
from axiom.tools.registry import ToolContext


def git_available() -> bool:
    return shutil.which("git") is not None


async def _git(args: str, workspace: str, timeout: float = 30.0) -> tuple[int, str]:
    code, out, err = await run_shell(f"git {args}", workspace, timeout=timeout)
    output = (out + ("\n" + err if err.strip() else "")).strip()
    return code, output


async def git_status(_context: ToolContext) -> ToolResult:
    code, out = await _git("status --short --branch", _context.workspace)
    return ToolResult(tool_call_id="", name="git_status", content=out or "(clean)", is_error=code != 0)


async def git_diff(_context: ToolContext, staged: bool = False) -> ToolResult:
    flag = "--cached" if staged else ""
    code, out = await _git(f"diff {flag}".strip(), _context.workspace)
    out = out[:20000]
    return ToolResult(tool_call_id="", name="git_diff", content=out or "(no diff)", is_error=code != 0)


async def git_log(_context: ToolContext, limit: int = 10) -> ToolResult:
    code, out = await _git(f"log --oneline -{limit}", _context.workspace)
    return ToolResult(tool_call_id="", name="git_log", content=out, is_error=code != 0)


async def git_branch(_context: ToolContext) -> ToolResult:
    code, out = await _git("branch -a", _context.workspace)
    return ToolResult(tool_call_id="", name="git_branch", content=out, is_error=code != 0)


async def git_checkout(_context: ToolContext, branch: str, create: bool = False) -> ToolResult:
    flag = "-b " if create else ""
    code, out = await _git(f"checkout {flag}{branch}", _context.workspace)
    return ToolResult(tool_call_id="", name="git_checkout", content=out, is_error=code != 0)


async def git_commit(_context: ToolContext, message: str, add_all: bool = True) -> ToolResult:
    if add_all:
        code, out = await _git("add -A", _context.workspace)
        if code != 0:
            return ToolResult(tool_call_id="", name="git_commit", content=out, is_error=True)
    # Guard: never commit files that look like secret stores.
    code, check = await _git("status --porcelain -- .env .env.* credentials.json", _context.workspace)
    if check.strip():
        return ToolResult(
            tool_call_id="", name="git_commit",
            content="Error: refusing to commit: secret-like files staged (.env / credentials).",
            is_error=True,
        )
    quoted = message.replace('"', '\\"')
    code, out = await _git(f'commit -m "{quoted}"', _context.workspace)
    return ToolResult(tool_call_id="", name="git_commit", content=out, is_error=code != 0)
