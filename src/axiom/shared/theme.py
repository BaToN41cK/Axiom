"""AXIOM visual identity — palette, glyphs and animation frames.

Pure data only (no UI framework imports, no state): every frontend renders the
same identity, and the TUI adapts these values into a Textual theme.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------- palette
# Absolute black, deep obsidian burgundy accents, ash greys. Garnet is used
# sparingly: active states, logo, selection, progress, thin separators.

BLACK = "#000000"
VOID = "#050505"
OBSIDIAN = "#080808"
ASH_DEEP = "#161616"
ASH = "#262626"
ASH_SOFT = "#3A3A3A"
MUTED = "#777777"
SILVER = "#B9B9B9"
WHITE = "#FFFFFF"

#: The single accent family — never brighter than this (no scarlet, no neon).
GARNET = "#4A0E14"
GARNET_DEEP = "#3B0A10"
GARNET_DIM = "#2A070C"
GARNET_GLOW = "#6B141C"
GARNET_ASH = "#8A6A6E"

#: bronze/stone tones used for secondary detail
BRONZE = "#6E5A3A"
STONE = "#4A4642"

#: semantic colours (kept desaturated to stay inside the atmosphere)
SUCCESS = "#7E9E86"
ERROR = "#8E3038"
WARNING = "#9A8352"

# ------------------------------------------------------------------- text style
LOGO_STYLE = f"bold {WHITE}"
TAGLINE_STYLE = MUTED
ACCENT_STYLE = f"bold {GARNET_GLOW}"

# ----------------------------------------------------------------------- glyphs
PROMPT_GLYPH = "❯"
TICK = "✓"
CROSS = "✕"
INTERRUPTED = "■"
DOT_ACTIVE = "●"
DOT_IDLE = "○"
ARROW = "›"
BULLET = "·"
DIAMOND = "◆"
RING = "◌"
SEARCH_GLYPH = "◉"
TOOL_GLYPH = "⬢"
ANSWER_GLYPH = "◆"
TREE_BRANCH = "├─"
TREE_LAST = "└─"
TREE_PIPE = "│"
SEPARATOR = "│"

#: Smooth spinner — deliberately round, never ASCII noise.
SPINNER_FRAMES = ("◌", "◔", "◑", "◕")
SPINNER_INTERVAL = 0.12

#: Slash-command / panel separators
LINE_THIN = "─"
LINE_DOT = "┄"
CORNER_TL = "╭"
CORNER_TR = "╮"
CORNER_BL = "╰"
CORNER_BR = "╯"
PANEL_LEFT = "│"
PANEL_RIGHT = "│"

#: Glyphs for the generation state machine.
STATE_GLYPHS: dict[str, str] = {
    "idle": DOT_IDLE,
    "connecting": "◌",
    "thinking": "◌",
    "tool_call": "◌",
    "searching": "◌",
    "receiving": "◌",
}

#: Human labels for the state machine (frontends may override).
STATE_LABELS: dict[str, str] = {
    "idle": "Idle",
    "connecting": "Connecting",
    "thinking": "Thinking",
    "tool_call": "Tool",
    "searching": "Searching web",
    "receiving": "Generating",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "error": "Failed",
}

#: Whether the AXIOM palette is a dark theme.
THEME_DARK = True
#: How much Textual is allowed to spread the palette's luminosity.
THEME_LUMINOSITY_SPREAD = 0.12

#: Live phase titles — the timeline vocabulary of the AXIOM design language.
PHASE_THINKING = "THINKING"
PHASE_SEARCH = "WEB SEARCH"
PHASE_TOOL = "TOOL"
PHASE_ANSWER = "ANSWER"
PHASE_SOURCES = "SOURCES"

#: The theme registered with Textual (keys match textual.theme.Theme fields).
#: Values are typed as ``Any`` because Textual expects a mix of ``str``,
#: ``bool`` and ``float``; the TUI is the only place that adapts these
#: values into a ``textual.theme.Theme``.
THEME_COLORS: dict[str, Any] = {
    "name": "obsidian",
    "primary": GARNET_GLOW,
    "secondary": GARNET,
    "accent": GARNET_GLOW,
    "foreground": WHITE,
    "background": BLACK,
    "surface": OBSIDIAN,
    "panel": ASH_DEEP,
    "boost": ASH,
    "warning": WARNING,
    "error": ERROR,
    "success": SUCCESS,
    "dark": THEME_DARK,
    "luminosity_spread": THEME_LUMINOSITY_SPREAD,
}

#: Name of the theme as it is registered with the TUI framework.
THEME_NAME = "obsidian"
