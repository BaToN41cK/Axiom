"""``@mention`` expansion — turn ``@src/main.py`` into the real file content.

When the user drags a file from the Explorer (or types ``@path``), the stored
history keeps the honest short form — what the user actually typed — while the
model request carries the real file content. Expansion is deliberately
conservative: only paths that resolve INSIDE the workspace and exist on disk
are expanded; anything else (emails, twitter handles) passes through untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

#: ``@relative/path.ext`` or ``@nested/dir/file.py`` — must contain a slash or
#: start-of-path word and end with a real-looking extension. Emails
#: (``user@host.tld``) never match because the ``@`` must start a token.
MENTION_RE = re.compile(r"(?<![\w@.])@(?P<path>[\w.~+-]+(?:[\\/][\w.~+-]+)*)")

#: Per-file and per-message expansion budgets — a mention must never bloat the
#: prompt beyond what a local model can comfortably eat.
MAX_FILE_CHARS = 24_000
MAX_TOTAL_CHARS = 60_000
MAX_MENTIONS = 5

_TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".txt", ".toml",
    ".yaml", ".yml", ".css", ".html", ".rs", ".go", ".c", ".h", ".cpp",
    ".sh", ".cfg", ".ini", ".sql", ".svg", ".xml", ".csv", ".env",
}


def _resolve(root: Path, rel: str) -> Path | None:
    """Resolve ``rel`` strictly inside ``root``; ``None`` when not a file."""
    if not rel or any(part == ".." for part in rel.replace("\\", "/").split("/")):
        return None
    candidate = (root / rel).resolve()
    if candidate == root or root not in candidate.parents:
        return None
    try:
        if candidate.is_file() and candidate.suffix.lower() in _TEXT_SUFFIXES:
            return candidate
    except OSError:
        return None
    return None


def expand_mentions(text: str, root: Path | None) -> str:
    """Replace existing ``@path`` mentions with fenced file content.

    Non-existing paths, non-workspace paths and non-text files stay as typed.
    ``root is None`` (no workspace) returns the text unchanged.
    """
    if root is None or "@" not in text:
        return text
    try:
        root = root.resolve()
    except OSError:
        return text

    budget = MAX_TOTAL_CHARS
    expanded = 0
    used = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal budget, expanded, used
        if expanded >= MAX_MENTIONS or budget <= 0:
            return match.group(0)
        rel = match.group("path")
        target = _resolve(root, rel)
        if target is None:
            return match.group(0)
        try:
            body = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return match.group(0)
        if len(body) > MAX_FILE_CHARS:
            body = body[:MAX_FILE_CHARS] + "\n… truncated"
        cost = len(body)
        if cost > budget:
            body = body[:budget] + "\n… truncated"
            cost = budget
        budget -= cost
        expanded += 1
        used += 1
        lang = target.suffix.lstrip(".") or "text"
        return (
            f"{match.group(0)}\n```{lang}  # {rel}\n{body}\n```"
        )

    out = MENTION_RE.sub(replace, text)
    return out
