"""AXIOM startup: logo, initialization sequence and error screens."""

import asyncio

import httpx
from rich.panel import Panel
from rich.text import Text

from src.config import config
from src.ui.theme import SYMBOLS
from src.ui.renderer import console

AXIOM_LOGO = """\
 █████╗ ██╗  ██╗██╗ ██████╗ ███╗   ███╗
██╔══██╗╚██╗██╔╝██║██╔═══██╗████╗ ████║
███████║ ╚███╔╝ ██║██║   ██║██╔████╔██║
██╔══██║ ██╔██╗ ██║██║   ██║██║╚██╔╝██║
██║  ██║██╔╝ ██╗██║╚██████╔╝██║ ╚═╝ ██║
╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝     ╚═╝
"""


def render_logo() -> Text:
    """Render the AXIOM logo as the primary startup identity."""
    return Text("\n" + AXIOM_LOGO, style="axiom.logo")


async def run_initialization() -> bool:
    """Run the startup sequence under the logo.

    Shows live status lines for each real initialization step and a
    final `● READY` marker. Returns True when startup may continue.
    On failure the appropriate error panel is printed and False returned.
    """
    steps: list[tuple[str, str]] = []  # (name, state) state: done|failed

    def render_steps() -> Text:
        text = Text("\n")
        for name, state in steps:
            if state == "done":
                text.append(f"  {name:<28}", style="muted")
                text.append(f"{SYMBOLS['success']}\n", style="status.success")
            else:
                text.append(f"  {name:<28}", style="muted")
                text.append(f"{SYMBOLS['error']}\n", style="status.error")
        return text

    from rich.console import Group
    from rich.live import Live

    def display_step(name: str, state: str):
        steps.append((name, state))
        live.update(Group(render_logo(), render_steps()))

    # Live keeps the final frame (logo + steps) permanently on screen.
    with Live(Group(render_logo(), Text("\n")), console=console,
              refresh_per_second=10) as live:
        # 1. Local initialization — always succeeds.
        await asyncio.sleep(0.15)
        display_step("Initializing AXIOM", "done")

        # 2. Ollama connection.
        ok, _msg = await check_ollama_connection()
        display_step("Connecting to Ollama", "done" if ok else "failed")

        # 3. Model detection.
        model_ok = False
        if ok:
            model_ok, _msg, _models = await check_model_available()
        model_name, _, tag = config.model.partition(":")
        label = model_name.capitalize() + (f" {tag.upper()}" if tag else "")
        display_step(f"Detecting {label}", "done" if model_ok else "failed")

        # 4. Web tools.
        display_step("Initializing Web", "done" if config.web_enabled else "failed")

        await asyncio.sleep(0.2)

    # Initialization finished — show READY, then errors if any.
    ready = Text("\n  ● READY\n", style="success")
    console.print(ready)

    if not ok:
        console.print()
        console.print(render_ollama_not_found())
        console.print()
        return False
    if not model_ok:
        console.print()
        console.print(render_model_not_found(config.model))
        console.print()
        return False
    return True


async def check_ollama_connection() -> tuple[bool, str]:
    """Check if Ollama is running and accessible.
    
    Returns:
        Tuple of (success, message).
    """
    try:
        # trust_env=False prevents system proxies from intercepting
        # requests to the local Ollama server.
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.get(f"{config.ollama_host}/api/tags")
            if resp.status_code == 200:
                return True, "Ollama Connected"
            else:
                return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        return False, "Connection refused"
    except httpx.TimeoutException:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


async def check_model_available() -> tuple[bool, str, list[dict]]:
    """Check if the configured model is available.
    
    Returns:
        Tuple of (available, message, models_list).
    """
    try:
        # trust_env=False prevents system proxies from intercepting
        # requests to the local Ollama server.
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.get(f"{config.ollama_host}/api/tags")
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}", []

            data = resp.json()
            models = data.get("models", [])
            model_names = [m.get("name", "") for m in models]

            # Check for exact match or partial match
            if config.model in model_names:
                return True, f"{config.model} Ready", models

            # Check without tag
            model_base = config.model.split(":")[0]
            for name in model_names:
                if name.startswith(model_base):
                    return True, f"{config.model} Ready", models

            return False, f"{config.model} not found", models

    except Exception as e:
        return False, str(e), []


def render_model_not_found(model: str) -> Panel:
    """Render model not found error panel."""
    content = Text()
    content.append(f"\n  {model} is not installed.\n\n", style="bright_white")
    content.append("  Install it with:\n\n", style="muted")
    content.append(f"      ollama pull {model}\n", style="highlight")
    return Panel(
        content,
        title=f" {SYMBOLS['error']} MODEL NOT FOUND ",
        title_align="left",
        border_style="border.error",
        padding=(1, 2),
    )


def render_ollama_not_found() -> Panel:
    """Render Ollama not found error panel."""
    content = Text()
    content.append(f"\n  Cannot connect to Ollama.\n\n", style="bright_white")
    content.append("  Endpoint\n", style="muted")
    content.append(f"  {config.ollama_host}\n\n", style="value")
    content.append("  Start Ollama and try again.\n", style="muted")
    return Panel(
        content,
        title=f" {SYMBOLS['error']} CONNECTION ERROR ",
        title_align="left",
        border_style="border.error",
        padding=(1, 2),
    )
