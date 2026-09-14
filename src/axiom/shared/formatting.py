"""Shared presentation helpers — plain data formatting, no UI frameworks.

Everything here is pure: no I/O, no state, no model calls. Frontends use these
functions so that the CLI, TUI and a future GUI render identical information.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from axiom.shared.theme import (
    CROSS,
    DOT_ACTIVE,
    DOT_IDLE,
    MUTED,
    SPINNER_FRAMES,
    STATE_LABELS,
    TICK,
)

# ------------------------------------------------------------------ time / size


def format_duration(seconds: float) -> str:
    """``4.8s`` / ``1m 12s`` — durations only ever come from real timings."""
    if seconds < 0:
        seconds = 0.0
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}m {rest}s"


def format_duration_ms(milliseconds: int | None) -> str:
    """Milliseconds → compact duration (empty string when unknown)."""
    if not milliseconds or milliseconds <= 0:
        return ""
    return format_duration(milliseconds / 1000)


def format_tokens(count: int | None) -> str:
    """``2.4k`` / ``118`` — formats a real token count, never an estimate."""
    if count is None:
        return "—"
    if count < 1000:
        return str(count)
    if count < 1_000_000:
        return f"{count / 1000:.1f}k"
    return f"{count / 1_000_000:.1f}M"


def format_rate(tokens_per_second: float | None) -> str:
    """``18.6 tok/s`` — real throughput reported by Ollama."""
    if tokens_per_second is None:
        return ""
    return f"{tokens_per_second:.1f} tok/s"


def format_clock(timestamp: float | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%H:%M")


def history_bucket(timestamp: float) -> str:
    """Group conversations into Today / Yesterday / date labels."""
    moment = datetime.fromtimestamp(timestamp).date()
    today = datetime.now().date()
    if moment == today:
        return "Today"
    if moment == today - timedelta(days=1):
        return "Yesterday"
    if moment.year == today.year:
        return moment.strftime("%d %b")
    return moment.strftime("%d %b %Y")


def elapsed_since(started: float) -> float:
    return max(0.0, time.perf_counter() - started)


# ----------------------------------------------------------------- texts / glyphs


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Collapse whitespace and cut to *width* characters."""
    text = " ".join(text.split())
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= len(ellipsis):
        return text[:width]
    return text[: width - len(ellipsis)].rstrip() + ellipsis


def one_line(text: str, width: int = 80) -> str:
    """First meaningful line of *text*, truncated for list rows."""
    for line in text.splitlines():
        stripped = line.strip().lstrip("#>*-• ").strip()
        if stripped:
            return truncate(stripped, width)
    return ""


def spinner_frame(tick: int) -> str:
    """Frame of the smooth circular spinner (never an ASCII spinner)."""
    return SPINNER_FRAMES[tick % len(SPINNER_FRAMES)]


def status_glyph(state_value: str, *, done: bool = False, failed: bool = False) -> str:
    """``✓`` / ``✕`` / ◌ for any state-machine state."""
    if failed or state_value == "error":
        return CROSS
    if done or state_value == "completed":
        return TICK
    if state_value == "idle":
        return DOT_IDLE
    return DOT_ACTIVE


def status_label(state_value: str) -> str:
    return STATE_LABELS.get(state_value, state_value.capitalize())


def status_line(
    state_value: str,
    *,
    tick: int = 0,
    duration_ms: int | None = None,
    detail: str | None = None,
    active: bool = False,
) -> str:
    """Compose ``Thinking ◌`` / ``Thinking ✓ 4.8s`` style status text.

    Renders only what the state machine actually reported — it never invents
    progress or a duration.
    """
    label = status_label(state_value)
    failed = state_value == "error"
    done = not active and not failed and state_value not in ("idle",)
    if active and not failed:
        glyph = spinner_frame(tick)
    else:
        glyph = status_glyph(state_value, done=done, failed=failed)
    parts = [f"{label} {glyph}"]
    duration = format_duration_ms(duration_ms)
    if duration:
        parts.append(duration)
    if detail:
        parts.append(f"· {detail}")
    return "  ".join(parts)


def message_roles() -> dict[str, str]:
    """Canonical role labels used by every frontend."""
    return {"user": "YOU", "assistant": "AXIOM", "system": "SYSTEM", "tool": "TOOL"}


def wrap_text(text: str, width: int) -> list[str]:
    """Minimal word wrapper (used by non-Rich frontends such as the CLI)."""
    if width <= 1:
        return [text]
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for word in paragraph.split():
            if not current:
                current = word
            elif len(current) + 1 + len(word) <= width:
                current += " " + word
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def render_plain_exchange(role: str, text: str, width: int = 80) -> str:
    """Plain-text rendering of one message (used by the CLI frontend)."""
    label = message_roles().get(role, role.upper())
    body = "\n".join(wrap_text(text.strip(), width))
    return f"{label}\n\n{body}\n"


def muted(text: str) -> str:
    """Rich-markup muted style (accepted by Textual/Rich widgets)."""
    return f"[{MUTED}]{text}[/]"


def sources_listing(sources) -> str:
    """Numbered source list shared by CLI and TUI rendering."""
    lines = []
    for source in sources:
        index = getattr(source, "index", 0)
        lines.append(f"{index:02d}  {getattr(source, 'title', '')}")
        url = getattr(source, "url", "")
        if url:
            lines.append(f"    {url}")
    return "\n".join(lines)