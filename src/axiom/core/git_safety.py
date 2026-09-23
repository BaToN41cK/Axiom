"""Git Safety Layer (п.12/22): checkpoint до правок, diff-статистика, revert."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Checkpoint:
    root: str
    ref: str
    dirty_before: str = ""


def _git(root: Path, *args: str, timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=timeout, check=False)


def create_checkpoint(root: Path | str) -> Checkpoint:
    base = Path(root).resolve()
    dirty = ""
    try:
        dirty = _git(base, "status", "--short").stdout.strip()[:4000]
    except Exception:
        pass
    ref = "no-git"
    try:
        head = _git(base, "rev-parse", "HEAD").stdout.strip()
        if head:
            ref = head
        else:
            empty = _git(base, "stash", "create").stdout.strip()
            ref = f"stash:{empty}" if empty else "dirty-no-head"
    except Exception:
        ref = "error"
    return Checkpoint(root=str(base), ref=ref, dirty_before=dirty)


def diff_stats(root: Path | str) -> dict:
    base = Path(root).resolve()
    try:
        proc = _git(base, "diff", "--numstat")
        files = 0
        added = 0
        removed = 0
        for line in (proc.stdout or "").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                files += 1
                try:
                    added += int(parts[0]) if parts[0] != "-" else 0
                    removed += int(parts[1]) if parts[1] != "-" else 0
                except ValueError:
                    continue
        return {"files": files, "added": added, "removed": removed}
    except Exception:
        return {"files": 0, "added": 0, "removed": 0}


def revert_to_checkpoint(checkpoint: Checkpoint) -> dict:
    base = Path(checkpoint.root)
    if checkpoint.ref == "no-git" or checkpoint.ref == "error":
        return {"ok": False, "error": "not a git repo or checkpoint failed"}
    if checkpoint.ref.startswith("stash:"):
        return {"ok": False, "error": "no HEAD yet: review changes manually"}
    try:
        proc = _git(base, "reset", "--hard", checkpoint.ref)
        if proc.returncode != 0:
            return {"ok": False, "error": (proc.stderr or proc.stdout).strip()[:1000]}
        return {"ok": True, "ref": checkpoint.ref}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
