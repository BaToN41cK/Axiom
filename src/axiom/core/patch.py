"""Apply a unified diff (a ```diff block from a model answer) to a file.

The applier is strict on purpose: every hunk must match the current file
content exactly, otherwise nothing is written — a half-applied patch is worse
than a rejected one. All paths stay inside the workspace (the caller resolves
and sandboxes them; this module only transforms text → text).
"""

from __future__ import annotations

import re

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    """The patch is malformed or does not match the target file."""


def _parse_hunks(patch: str) -> list[tuple[int, list[str]]]:
    """Split a unified diff into ``(old_start, lines)`` hunks (1-based start)."""
    hunks: list[tuple[int, list[str]]] = []
    current: tuple[int, list[str]] | None = None
    for raw in patch.splitlines():
        if raw.startswith("---") or raw.startswith("+++"):
            continue  # file headers — the caller decides the target path
        header = _HUNK_RE.match(raw)
        if header:
            if current is not None:
                hunks.append(current)
            current = (int(header.group(1)), [])
            continue
        if current is None:
            if raw.startswith("diff ") or raw.startswith("index ") or not raw.strip():
                continue
            raise PatchError(f"Content outside of any hunk: {raw!r}")
        if raw.startswith("\\"):  # "\ No newline at end of file"
            continue
        if not raw:
            # Some generators emit bare empty lines instead of " " context.
            current[1].append(" ")
            continue
        if raw[0] in " +-":
            current[1].append(raw)
            continue
        raise PatchError(f"Unknown patch line: {raw!r}")
    if current is not None:
        hunks.append(current)
    if not hunks:
        raise PatchError("The patch contains no hunks")
    return hunks


def apply_unified_diff(original: str, patch: str) -> str:
    """Return ``original`` with ``patch`` applied, or raise :class:`PatchError`.

    Hunks are applied top-to-bottom against the ORIGINAL line numbering (each
    hunk header refers to the pre-image), which is exactly what unified diffs
    specify — no iteration order tricks needed for well-formed patches.
    """
    src = original.split("\n") if original else []
    hunks = _parse_hunks(patch)
    out: list[str] = []
    cursor = 0  # 0-based index into src
    for start, lines in hunks:
        target = max(start - 1, 0)
        if target > len(src):
            raise PatchError(f"Hunk starts beyond end of file (line {start})")
        out.extend(src[cursor:target])
        cursor = target
        for line in lines:
            tag, body = line[0], line[1:]
            if tag in " -":
                if cursor >= len(src) or src[cursor] != body:
                    got = src[cursor] if cursor < len(src) else "<EOF>"
                    raise PatchError(
                        f"Context mismatch at line {cursor + 1}: expected {body!r}, got {got!r}"
                    )
                if tag == " ":
                    out.append(body)
                cursor += 1
            elif tag == "+":
                out.append(body)
    out.extend(src[cursor:])
    return "\n".join(out)


def extract_target_path(patch: str) -> str | None:
    """Best-effort target path from the ``+++ b/...`` header (``None`` if absent)."""
    for line in patch.splitlines():
        if line.startswith("+++"):
            path = line[3:].strip()
            if path in ("/dev/null", ""):
                return None
            return re.sub(r"^[ab]/", "", path)
    return None
