"""AXIOM logo — the main visual element of the splash screen.

The art lives here as data (and is mirrored in ``assets/logo.txt`` so the repo
has a visible asset). It renders correctly in a standard Windows terminal.
"""

from __future__ import annotations

from pathlib import Path

#: ANSI-shadow "AXIOM" — 6 rows, 50 columns.
LOGO_ART: tuple[str, ...] = (
    "  █████╗  ██╗  ██╗ ██╗  ██████╗  ███╗   ███╗",
    " ██╔══██╗ ╚██╗██╔╝ ██║ ██╔═══██╗ ████╗ ████║",
    " ███████║  ╚███╔╝  ██║ ██║   ██║ ██╔████╔██║",
    " ██╔══██║  ██╔██╗  ██║ ██║   ██║ ██║╚██╔╝██║",
    " ██║  ██║ ██╔╝ ██╗ ██║ ╚██████╔╝ ██║ ╚═╝ ██║",
    " ╚═╝  ╚═╝ ╚═╝  ╚═╝ ╚═╝  ╚═════╝  ╚═╝     ╚═╝",
)

#: Compact variant for very narrow terminals (< 56 columns).
LOGO_COMPACT: tuple[str, ...] = (
    "▄▀█ ▀▄▀ █ █▀█ █▀▄▀█",
    "█▀█ █░█ █ █▄█ █░▀░█",
)

#: Thin flourish placed under the logo.
LOGO_RULE = "┄┄┄┄ ╪ ┄┄┄┄"

TITLE = "AXIOM"
SUBTITLE = "LOCAL INTELLIGENCE"

#: Width of the full artwork.
LOGO_WIDTH = max(len(line) for line in LOGO_ART)
COMPACT_WIDTH = max(len(line) for line in LOGO_COMPACT)


def logo_lines(width: int = 80) -> tuple[str, ...]:
    """Pick the artwork that fits the terminal width."""
    if width >= LOGO_WIDTH + 4:
        return LOGO_ART
    return LOGO_COMPACT


def logo_frame(offset: int, width: int = 80) -> list[str]:
    """Return the logo shifted vertically by *offset* rows.

    Used by the splash animation (a slow 1-second bounce). Negative offsets
    move the logo upward, positive downward; the result always keeps the same
    number of rows so the layout never jumps.
    """
    lines = list(logo_lines(width))
    rows = len(lines)
    offset = max(-rows, min(rows, offset))
    if offset > 0:
        shifted = [""] * offset + lines
    elif offset < 0:
        shifted = lines[-offset:] + [""] * (-offset)
    else:
        shifted = lines
    return shifted[:rows]


def load_logo_asset(path: Path | None = None) -> tuple[str, ...] | None:
    """Read ``assets/logo.txt`` if present (falls back to the built-in art)."""
    asset = path
    if asset is None:
        candidate = Path(__file__).resolve().parents[3] / "assets" / "logo.txt"
        asset = candidate if candidate.exists() else None
    if asset is None or not asset.exists():
        return None
    try:
        lines = asset.read_text(encoding="utf-8").rstrip("\n").splitlines()
    except OSError:
        return None
    lines = [line for line in lines if line.strip()]
    return tuple(lines) or None
