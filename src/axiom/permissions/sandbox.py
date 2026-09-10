"""Sandbox backends and workspace boundary validation.

Note: this is a workspace-boundary guard, NOT an OS-level sandbox.
The SandboxBackend interface exists so Docker / Windows Sandbox
backends can be added later.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from axiom.core.errors import WorkspaceBoundaryError
from axiom.core.logging import get_logger

logger = get_logger("sandbox")


class SandboxBackend(Protocol):
    """Interface for future sandbox implementations (Docker etc.)."""

    async def run_command(self, command: list[str], workspace: str) -> tuple[int, str, str]:
        """Run a command inside the sandbox; return (exit_code, stdout, stderr)."""
        ...


class LocalBackend:
    """Executes directly on the host (default backend, no isolation)."""

    async def run_command(self, command: list[str], workspace: str) -> tuple[int, str, str]:
        import asyncio

        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _same_path(candidate: Path, root: Path) -> bool:
    """Case-insensitive containment check that also catches drive-relative escapes."""
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def validate_workspace_path(
    raw_path: str,
    workspace: str,
    *,
    follow_symlinks: bool = True,
    must_exist: bool = False,
) -> Path:
    """Resolve and validate a path against the workspace boundary.

    Raises WorkspaceBoundaryError on traversal / absolute-escape / symlink escape.
    """
    ws = Path(workspace).resolve()
    raw = raw_path.strip()
    if not raw:
        return ws

    candidate = Path(raw)
    if candidate.is_absolute():
        resolved_candidate = candidate.resolve(strict=False) if follow_symlinks else candidate
        if not _same_path(resolved_candidate, ws):
            raise WorkspaceBoundaryError(raw_path, str(ws))
        path = resolved_candidate
    else:
        path = ws / candidate
        resolved_candidate = path.resolve(strict=False)
        if not _same_path(resolved_candidate, ws):
            raise WorkspaceBoundaryError(raw_path, str(ws))
        path = resolved_candidate

    # Symlink escape check for existing parents.
    if follow_symlinks and path.exists():
        real = Path(os.path.realpath(path))
        if not _same_path(real, ws):
            logger.warning("Symlink escape blocked: %s -> %s", path, real)
            raise WorkspaceBoundaryError(raw_path, str(ws))
    else:
        # Walk the existing part of the parent chain.
        check = path.parent
        while not check.exists() and check != check.parent:
            check = check.parent
        if check.exists():
            real = Path(os.path.realpath(check))
            if not _same_path(real, ws):
                raise WorkspaceBoundaryError(raw_path, str(ws))

    if must_exist and not path.exists():
        from axiom.core.errors import AxiomError

        raise FileNotFoundError(str(path))

    return path


def is_path_inside_workspace(raw_path: str, workspace: str) -> bool:
    try:
        validate_workspace_path(raw_path, workspace)
        return True
    except WorkspaceBoundaryError:
        return False
