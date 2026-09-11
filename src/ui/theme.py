"""AXIOM color theme and visual styling."""

from rich.theme import Theme

# AXIOM color palette — minimal, professional, technological
AXIOM_THEME = Theme({
    "axiom": "bold bright_cyan",
    "axiom.logo": "bold bright_cyan",
    "axiom.dim": "dim bright_cyan",
    "axiom.title": "bold white on dark_blue",
    "header": "bold bright_cyan",
    "header.model": "bold bright_white",
    "user": "bold bright_white",
    "assistant": "bright_white",
    "status": "dim white",
    "status.active": "bold bright_cyan",
    "status.success": "bold green",
    "status.warning": "bold yellow",
    "status.error": "bold red",
    "status.ready": "bold green",
    "status.thinking": "bold bright_cyan",
    "status.generating": "bold bright_cyan",
    "thinking": "dim white",
    "thinking.text": "dim italic white",
    "plan": "bright_white",
    "plan.header": "bold bright_cyan",
    "search": "bright_white",
    "search.header": "bold bright_cyan",
    "source": "dim white",
    "source.url": "dim blue",
    "border": "dim bright_cyan",
    "border.strong": "bright_cyan",
    "border.header": "bright_cyan",
    "border.error": "red",
    "border.warning": "yellow",
    "border.success": "green",
    "input": "bright_white",
    "input.prompt": "bold bright_cyan",
    "panel.title": "bold bright_cyan",
    "panel.border": "dim bright_cyan",
    "divider": "dim bright_cyan",
    "muted": "dim white",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "info": "bright_cyan",
    "label": "dim white",
    "value": "bright_white",
    "highlight": "bold bright_cyan",
    "tree": "bright_cyan",
    "tree.selected": "bold bright_white on dark_blue",
})

# Status indicators
SYMBOLS = {
    "ready": "●",
    "active": "◐",
    "success": "✓",
    "error": "✗",
    "warning": "⚠",
    "info": "ℹ",
    "bullet": "•",
    "arrow": "→",
    "separator": "│",
}

# Status colors by state
STATUS_COLORS = {
    "ready": "green",
    "generating": "bright_cyan",
    "thinking": "bright_cyan",
    "searching": "bright_cyan",
    "researching": "bright_cyan",
    "planning": "bright_cyan",
    "reasoning": "bright_cyan",
    "error": "red",
    "warning": "yellow",
}
