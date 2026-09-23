"""Git tools — read-only inspection of the workspace repository.

All operations are real ``git`` subprocess calls inside the workspace root.
Only safe read-only subcommands are exposed (``status``, ``diff``, ``log``,
``branch``); commit/push are intentionally NOT agent tools — the user runs
them manually (optionally drafted by the agent) so every history rewrite
stays confirmed (§17).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from axiom.core.tools.base import ToolDefinition, ToolPermission, ToolResult
from axiom.core.tools.filesystem import default_workspace_root

GIT_STATUS_TOOL = "git_status"
GIT_DIFF_TOOL = "git_diff"
GIT_LOG_TOOL = "git_log"
GIT_BRANCH_TOOL = "git_branch"

GIT_TOOLS = (GIT_STATUS_TOOL, GIT_DIFF_TOOL, GIT_LOG_TOOL, GIT_BRANCH_TOOL)

_TIMEOUT = 15.0
_MAX_CHARS = 12_000


class GitTools:
    """Registers real, read-only git inspection tools."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_workspace_root()).resolve()

    def set_root(self, root: Path) -> None:
        self.root = root.resolve()

    # ------------------------------------------------------------- helpers

    def _run_git(self, args: list[str]) -> ToolResult:
        if not (self.root / ".git").exists():
            return ToolResult(name="git", ok=False, error="Not a git repository")
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=self.root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                check=False,
            )
        except FileNotFoundError:
            return ToolResult(name="git", ok=False, error="git executable not found")
        except subprocess.SubprocessError as exc:
            return ToolResult(name="git", ok=False, error=f"git failed: {exc}")
        out = (proc.stdout or "")[:_MAX_CHARS]
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return ToolResult(name="git", ok=False, error=err or f"git exit {proc.returncode}", content=out)
        return ToolResult(name="git", ok=True, content=out.strip() or "(clean)")

    def _def(self, name: str, desc: str, extra: dict | None = None) -> ToolDefinition:
        props: dict = {"type": "object", "properties": {}, "required": []}
        if extra:
            props["properties"] = extra
        return ToolDefinition(name=name, description=desc, parameters=props, permission=ToolPermission.ALWAYS)

    # ---------------------------------------------------------- registration

    def register(self, registry) -> None:
        registry.register(
            self._def(GIT_STATUS_TOOL, "Show `git status --short --branch` of the workspace repo."),
            self._status,
        )
        registry.register(
            self._def(GIT_DIFF_TOOL, "Show `git diff` (unstaged changes).", {"ref": {"type": "string"}}),
            self._diff,
        )
        registry.register(
            self._def(GIT_LOG_TOOL, "Show recent commits (`git log --oneline -n`).", {"limit": {"type": "integer"}}),
            self._log,
        )
        registry.register(
            self._def(GIT_BRANCH_TOOL, "Show current branch and all local branches."),
            self._branch,
        )

    # -------------------------------------------------------------- handlers

    async def _status(self) -> ToolResult:
        res = self._run_git(["status", "--short", "--branch"])
        res.name = GIT_STATUS_TOOL
        return res

    async def _diff(self, ref: str | None = None) -> ToolResult:
        args = ["diff", "--no-color"]
        if ref and ref.strip():
            args.append(ref.strip())
        res = self._run_git(args)
        res.name = GIT_DIFF_TOOL
        return res

    async def _log(self, limit: int | None = None) -> ToolResult:
        n = max(1, min(int(limit or 10), 50))
        res = self._run_git(["log", f"-n{n}", "--oneline", "--decorate"])
        res.name = GIT_LOG_TOOL
        return res

    async def _branch(self) -> ToolResult:
        res = self._run_git(["branch", "--show-current"])
        if not res.ok:
            res.name = GIT_BRANCH_TOOL
            return res
        current = res.content.strip()
        all_branches = self._run_git(["branch", "--list"])
        body = f"Current: {current or '(detached)'}\n{all_branches.content}".strip()
        return ToolResult(name=GIT_BRANCH_TOOL, ok=True, content=body)


# ---------------------------------------------------------------- user git ops
#
# Write operations (stage / unstage / commit) are intentionally NOT registered
# as agent tools (§17: the model never rewrites history on its own). The GUI
# calls these helpers directly from the user's own button clicks, sandboxed to
# the workspace root like every other path handling here.


def _resolve_in_root(root: Path, rel: str) -> Path:
    """Resolve ``rel`` strictly inside ``root`` or raise ValueError."""
    clean = (rel or "").strip()
    if not clean:
        raise ValueError("Path is empty")
    if any(part == ".." for part in clean.replace("\\", "/").split("/")):
        raise ValueError(f"Path escapes the repository: {rel}")
    full = (root / clean).resolve()
    if full != root and root not in full.parents:
        raise ValueError(f"Path escapes the repository: {rel}")
    return full


def git_stage(root: Path, paths: list[str]) -> str:
    """``git add`` the given workspace-relative paths. Returns git output."""
    if not (root / ".git").exists():
        raise ValueError("Not a git repository")
    resolved = [str(_resolve_in_root(root, p)) for p in paths] or ["-A"]
    proc = subprocess.run(
        ["git", "add", "--", *resolved],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError((proc.stderr or proc.stdout or "git add failed").strip())
    return proc.stdout.strip()


def git_unstage(root: Path, paths: list[str]) -> str:
    """``git restore --staged`` the given paths (all staged when empty)."""
    if not (root / ".git").exists():
        raise ValueError("Not a git repository")
    if paths:
        resolved = [str(_resolve_in_root(root, p)) for p in paths]
        args = ["git", "restore", "--staged", "--", *resolved]
    else:
        args = ["git", "reset", "--quiet"]
    proc = subprocess.run(
        args,
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError((proc.stderr or proc.stdout or "git reset failed").strip())
    return proc.stdout.strip()


def git_commit(root: Path, message: str, *, all: bool = False) -> str:
    """Commit staged changes (optionally staging everything first)."""
    if not (root / ".git").exists():
        raise ValueError("Not a git repository")
    clean = (message or "").strip()
    if not clean:
        raise ValueError("Commit message is empty")
    args = ["git", "commit", "-m", clean]
    if all:
        args.insert(2, "-a")
    proc = subprocess.run(
        args,
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError((proc.stderr or proc.stdout or "git commit failed").strip())
    return proc.stdout.strip() or "Committed."


def git_diff_file(root: Path, path: str = "") -> str:
    """Unified diff of one file (staged + unstaged vs HEAD), new files included."""
    if not (root / ".git").exists():
        raise ValueError("Not a git repository")
    target = str(_resolve_in_root(root, path)) if path else None
    args = ["git", "diff", "--no-color", "HEAD", "--"]
    if target:
        args.append(target)
    proc = subprocess.run(
        args,
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        check=False,
    )
    diff = proc.stdout
    if not diff.strip() and target:
        # Untracked file: synthesize a /dev/null → b/ unified diff.
        try:
            rel = Path(target).resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError("Path escapes the repository") from exc
        content = Path(target).read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        body = "\n".join(f"+{line}" for line in lines)
        diff = (
            f"--- /dev/null\n+++ b/{rel.as_posix()}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}\n"
        )
    if proc.returncode != 0 and not diff.strip():
        raise ValueError((proc.stderr or "git diff failed").strip())
    return diff.rstrip() + "\n" if diff.strip() else ""


def git_switch(root: Path, branch: str) -> str:
    """``git switch`` to an existing local branch (user-initiated, §17)."""
    clean = (branch or "").strip()
    if not clean:
        raise ValueError("Branch name is empty")
    # A leading dash would make git parse the name as an option.
    if clean.startswith("-"):
        raise ValueError(f"Invalid branch name: {branch}")
    if not (root / ".git").exists():
        raise ValueError("Not a git repository")
    proc = subprocess.run(
        ["git", "switch", clean],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError((proc.stderr or proc.stdout or "git switch failed").strip())
    return proc.stdout.strip() or f"Switched to {clean}"
