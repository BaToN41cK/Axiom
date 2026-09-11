"""AXIOM main application — terminal UI and main loop.

The TUI is a live journal of the agent's work:
steps (Thinking / Planning / Search / Research / Reasoning) appear
as `◌ active` lines, flip to `✓ done` in place, and the finished task
stays in the scrollback as history. A persistent bottom HUD always
shows session statistics and the current agent state.
"""

import asyncio
import sys
from typing import Optional

from rich.console import Group
from rich.live import Live
from rich.text import Text

from src.config import config
from src.session import Session
from src.agent import Agent
from src.commands import handle_command, render_model_list
from src.ui.theme import SYMBOLS
from src.ui.renderer import (
    console,
    render_header,
    render_hud,
    render_user_message,
    render_assistant_header,
    render_divider,
    render_sources,
    render_markdown,
)
from src.ui.tasklog import TaskLog
from src.ui.input import InputReader

# Maps agent status events to journal step names and HUD states.
STEP_NAMES = {
    "thinking": "Thinking",
    "reasoning": "Reasoning",
    "planning": "Planning",
}
STATE_TEXT = {
    "ready": "READY",
    "thinking": "THINKING",
    "reasoning": "REASONING",
    "planning": "PLANNING",
    "generating": "GENERATING",
    "searching": "SEARCHING",
    "researching": "RESEARCHING",
}
# Max thinking characters shown live (kept secondary, dimmed).
_THINKING_PREVIEW = 400


class AxiomApp:
    """Main AXIOM application class."""

    def __init__(self):
        self.session = Session()
        self.agent = Agent(self.session)
        self.running = True
        self.generating = False

    async def startup(self):
        """Display the logo, run initialization, then enter the workspace."""
        from src.ui.startup import run_initialization

        console.print()
        ok = await run_initialization()
        if not ok:
            sys.exit(1)

        # Startup screen disappears — straight into the main TUI.
        console.print()
        console.print(render_header())
        console.print(render_divider())

    async def handle_input(self, user_input: str) -> Optional[str]:
        """Handle user input. Returns 'exit', 'new', or None."""
        user_input = user_input.strip()
        if not user_input:
            return None

        if user_input.startswith("/"):
            result = handle_command(user_input, self.session, self.agent)
            if result == "models":
                try:
                    models = await self.agent.ollama.list_models()
                    render_model_list(models)
                except Exception:
                    console.print("\n  Failed to fetch models.\n", style="status.error")
            return result

        await self.generate_response(user_input)
        return None

    async def generate_response(self, user_message: str):
        """Generate and display a response as a live agent-work journal."""
        self.generating = True
        tasklog = TaskLog()
        answer = Text()
        thinking_buf = [""]  # raw reasoning text (mutable, closure-safe)
        state = ["ready"]

        def render_frame() -> Group:
            """Compose the live frame: journal + streams + HUD."""
            parts = []
            log = tasklog.render()
            if log:
                parts.append(Text("\n"))
                parts.append(log)
            if thinking_buf[0]:
                parts.append(Text("\n"))
                parts.append(Text(thinking_buf[0], style="thinking.text"))
            if answer.plain:
                parts.append(Text("\n"))
                parts.append(answer)
            parts.append(Text("\n"))
            parts.append(render_hud(
                search=self.session.total_searches,
                tokens=self.session.formatted_tokens if self.session.total_tokens else "—",
                context_pct=self.session.context_percentage,
                tools=self.session.total_tools,
                state=state[0],
                state_text=STATE_TEXT.get(state[0], "READY"),
            ))
            return Group(*parts)

        def set_state(new_state: str):
            """Switch HUD state and refresh the live frame."""
            state[0] = new_state
            live.update(render_frame())

        def on_status(event: str, started: bool):
            """Update journal steps and HUD state."""
            if event == "generating":
                # Plain answer streaming — shown in HUD, no journal step.
                if started:
                    set_state("generating")
                return
            name = STEP_NAMES.get(event)
            if name is None:
                return
            if started:
                tasklog.start(name)
            else:
                tasklog.complete(name)
            set_state(event)

        def on_token(token: str, is_thinking: bool = False):
            """Append streaming tokens to the live frame."""
            if is_thinking:
                # Reasoning is visually secondary: dim and tail-limited.
                thinking_buf[0] = (thinking_buf[0] + token)[-_THINKING_PREVIEW:]
            else:
                answer.append(token)
            live.update(render_frame())

        def on_tool(name: str, args: dict, started: bool, result: Optional[dict] = None):
            """Update journal steps for tool executions."""
            if name == "web_search":
                if started:
                    query = args.get("query", "") if isinstance(args, dict) else ""
                    tasklog.start("Search", f"Searching for “{query}”..." if query else "")
                    set_state("searching")
                elif isinstance(result, dict) and result.get("error"):
                    tasklog.fail("Search", "failed")
                else:
                    count = result.get("count", 0) if isinstance(result, dict) else 0
                    tasklog.complete("Search", f"{count} results")
            elif name == "web_fetch":
                if started:
                    tasklog.start("Web Research", "Reading relevant sources...")
                    set_state("researching")
                elif isinstance(result, dict) and result.get("error"):
                    tasklog.fail("Web Research", "failed")
                else:
                    sources = self.agent.status.source_count
                    tasklog.complete("Web Research", f"{sources} sources")
            live.update(render_frame())

        console.print(render_user_message(user_message))
        console.print(render_assistant_header())

        result: dict = {}
        with Live(render_frame(), console=console, transient=True,
                  refresh_per_second=12) as live:
            try:
                result = await self.agent.process_message(
                    user_message,
                    on_token=on_token,
                    on_status=on_status,
                    on_tool=on_tool,
                )
            except KeyboardInterrupt:
                self.agent.cancel()
                result = {"success": False, "cancelled": True, "content": "", "error": "cancelled"}
            except Exception as e:
                result = {"success": False, "cancelled": False, "content": "", "error": str(e)}
            finally:
                set_state("ready")

        self.generating = False

        # The finished task becomes permanent scrollback history.
        if result.get("cancelled"):
            tasklog.cancel_active()
            console.print(tasklog.render())
            console.print(f"\n  {SYMBOLS['warning']} Cancelled\n", style="status.warning")
            console.print()
            return

        console.print(tasklog.render())

        content = result.get("content", "")
        if result.get("success") and content:
            console.print(render_divider())
            console.print(render_markdown(content))

            sources = self.agent.web.results
            if sources:
                console.print(render_sources(sources))

            console.print(f"\n  {SYMBOLS['success']} Answer completed\n", style="status.success")
        else:
            error = result.get("error", "Unknown error")
            console.print(f"\n  {SYMBOLS['error']} Task failed: {error}\n", style="status.error")
        console.print()

    def render_bottom_status(self) -> Text:
        """Render the persistent bottom HUD (idle state)."""
        return render_hud(
            search=self.session.total_searches,
            tokens=self.session.formatted_tokens if self.session.total_tokens else "—",
            context_pct=self.session.context_percentage,
            tools=self.session.total_tools,
            state="ready",
            state_text="READY",
        )

    async def run(self):
        """Main application loop."""
        await self.startup()
        reader = InputReader(on_clear=lambda: console.clear())
        while self.running:
            console.print(self.render_bottom_status())
            try:
                user_input = reader.read()
                reader.add(user_input)
            except (KeyboardInterrupt, EOFError):
                if self.generating:
                    self.agent.cancel()
                    self.generating = False
                    console.print()
                    continue
                else:
                    break
            console.print()
            result = await self.handle_input(user_input)
            if result == "exit":
                break
            elif result == "new":
                self.session = Session()
                self.agent = Agent(self.session)
                console.print()
        await self.agent.close()
        console.print(f"\n  {SYMBOLS['ready']} AXIOM closed.\n", style="muted")


def main():
    """Entry point for AXIOM."""
    app = AxiomApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        console.print(f"\n  {SYMBOLS['ready']} AXIOM closed.\n", style="muted")
        sys.exit(0)


if __name__ == "__main__":
    main()