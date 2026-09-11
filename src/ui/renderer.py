"""Rich rendering helpers for AXIOM UI."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.columns import Columns
from rich.align import Align

from src.config import config
from src.ui.theme import AXIOM_THEME, SYMBOLS, STATUS_COLORS

console = Console(theme=AXIOM_THEME, highlight=False)


def render_header() -> Text:
    """Render the main header bar, responsive to terminal width."""
    title = Text()
    title.append("  AXIOM", style="header")
    # Push the model name to the right edge on wide terminals,
    # keep it adjacent on narrow ones.
    gap = max(2, min(46, console.width - 10 - len(config.model) - 2))
    title.append(" " * gap)
    title.append(config.model, style="header.model")
    return title


def render_hud(
    search: int = 0,
    tokens: str = "—",
    context_pct: int = 0,
    tools: int = 0,
    state: str = "ready",
    state_text: str = "READY",
) -> Text:
    """Render the persistent bottom HUD bar."""
    color = STATUS_COLORS.get(state, "white")
    symbol = SYMBOLS["ready"] if state == "ready" else SYMBOLS["active"]
    sep = f" {SYMBOLS['separator']} "

    bar = Text()
    bar.append(f" SEARCH {search}", style="status")
    bar.append(f"{sep}TOKENS {tokens}", style="status")
    bar.append(f"{sep}CONTEXT {context_pct}%", style="status")
    bar.append(f"{sep}TOOLS {tools}", style="status")
    bar.append(sep, style="status")
    bar.append(f"{symbol} {state_text}", style=f"bold {color}")
    return bar


def render_user_message(message: str) -> Text:
    """Render user message label."""
    text = Text()
    text.append("\n  You\n", style="user")
    text.append(f"  {message}\n", style="bright_white")
    return text


def render_assistant_header() -> Text:
    """Render assistant response header."""
    text = Text()
    text.append("  AXIOM\n", style="assistant")
    return text


def render_divider() -> Text:
    """Render a horizontal divider, responsive to terminal width."""
    width = max(20, min(70, console.width - 2))
    return Text("  " + "─" * width + "\n", style="divider")


def render_sources(sources: list[dict]) -> Text:
    """Render sources list."""
    text = Text()
    text.append("\n  Sources\n", style="search.header")
    for i, source in enumerate(sources[: config.max_sources_display], 1):
        title = source.get("title", "Unknown")
        url = source.get("url", "")
        text.append(f"  [{i}] ", style="muted")
        text.append(f"{title}\n", style="source")
        if url:
            text.append(f"      {url}\n", style="source.url")
    return text


def render_error_panel(title: str, message: str, suggestion: str = "") -> Panel:
    """Render an error panel."""
    content = Text()
    content.append(f"  {message}\n", style="bright_white")
    if suggestion:
        content.append(f"\n  {suggestion}\n", style="muted")
    return Panel(
        content,
        title=f" {SYMBOLS['error']} {title} ",
        title_align="left",
        border_style="border.error",
        padding=(1, 2),
    )


def render_success_panel(title: str, message: str) -> Panel:
    """Render a success panel."""
    content = Text()
    content.append(f"  {message}\n", style="bright_white")
    return Panel(
        content,
        title=f" {SYMBOLS['success']} {title} ",
        title_align="left",
        border_style="border.success",
        padding=(1, 2),
    )


def render_info_panel(title: str, items: dict[str, str]) -> Panel:
    """Render an info panel with key-value pairs."""
    text = Text()
    for key, value in items.items():
        text.append(f"  {key:<16}", style="label")
        text.append(f"{value}\n", style="value")
    return Panel(
        text,
        title=f" {title} ",
        title_align="left",
        border_style="panel.border",
        padding=(1, 2),
    )


def render_markdown(text: str) -> Markdown:
    """Render markdown text."""
    return Markdown(text, code_theme="monokai")
