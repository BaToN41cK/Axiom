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
