"""AXIOM slash commands."""

from src.config import config
from src.ui.theme import SYMBOLS
from src.ui.renderer import console, render_info_panel


def render_help():
    """Render help information."""
    help_text = """
  AXIOM COMMANDS

  /help          Show this help message
  /status        Show connection and model status
  /model         Show current model
  /models        List available Ollama models
  /clear         Clear session history
  /thinking      Toggle thinking display
  /web           Toggle web tools
  /new           Start a new session
  /exit          Exit AXIOM

  KEYBOARD

  Enter          Send message
  Ctrl+C         Cancel generation
  Ctrl+L         Clear screen
  ↑ / ↓          Navigate input history
"""
    console.print(help_text, style="bright_white")


def render_status(ollama_status: str = "connected", model: str = ""):
    """Render status panel."""
    model = model or config.model
    items = {
        "Ollama": f"{SYMBOLS['ready']} {ollama_status}",
        "Model": model,
        "Reasoning": f"{SYMBOLS['ready']} Enabled" if config.reasoning_enabled else f"{SYMBOLS['error']} Disabled",
        "Web": f"{SYMBOLS['ready']} Enabled" if config.web_enabled else f"{SYMBOLS['error']} Disabled",
        "Files": f"{SYMBOLS['error']} Disabled",
        "PC Control": f"{SYMBOLS['error']} Disabled",
        "Memory": f"{SYMBOLS['error']} Disabled",
    }
    panel = render_info_panel("AXIOM STATUS", items)
    console.print(panel)


def render_current_model():
    """Render current model info."""
    console.print(f"\n  Model: ", style="label")
    console.print(f"{config.model}\n", style="value")


def render_model_list(models: list[dict]):
    """Render list of available models."""
    if not models:
        console.print("\n  No models found.\n", style="warning")
        return

    console.print("\n  Available Models\n", style="header")
    for m in models:
        name = m.get("name", "unknown")
        size = m.get("size", 0)
        # Format size
        if size > 1_000_000_000:
            size_str = f"{size / 1_000_000_000:.1f} GB"
        elif size > 1_000_000:
            size_str = f"{size / 1_000_000:.1f} MB"
        else:
            size_str = f"{size / 1_000:.1f} KB"

        marker = SYMBOLS['ready'] if name == config.model else SYMBOLS['bullet']
        style = "highlight" if name == config.model else "value"
        console.print(f"  {marker} {name:<30} {size_str}", style=style)
    console.print()


def handle_command(cmd: str, session=None, agent=None) -> "str | None":
    """Handle a slash command.
    
    Returns:
        'exit' to exit, 'new' for new session, None to continue.
    """
    parts = cmd.strip().lower().split()
    command = parts[0] if parts else ""

    if command == "/help":
        render_help()
    elif command == "/status":
        render_status(model=config.model)
    elif command == "/model":
        render_current_model()
    elif command == "/models":
        # Need to fetch models - handled by caller
        return "models"
    elif command == "/clear":
        if session:
            session.clear()
        console.print("\n  Session cleared.\n", style="status.success")
        return "clear"
    elif command == "/thinking":
        config.reasoning_enabled = not config.reasoning_enabled
        state = "enabled" if config.reasoning_enabled else "disabled"
        console.print(f"\n  Thinking {state}.\n", style="status.success")
    elif command == "/web":
        config.web_enabled = not config.web_enabled
        state = "enabled" if config.web_enabled else "disabled"
        console.print(f"\n  Web tools {state}.\n", style="status.success")
    elif command == "/new":
        if session:
            session.clear()
        console.print("\n  New session started.\n", style="status.success")
        return "new"
    elif command in ("/exit", "/quit", "/q"):
        return "exit"
    else:
        console.print(f"\n  Unknown command: {cmd}\n", style="status.error")
        console.print("  Type /help for available commands.\n", style="muted")

    return None
