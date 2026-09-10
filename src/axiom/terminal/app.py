"""Axiom TUI (Textual): branding header, streaming chat, tool activity, commands."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input, Static

from axiom.config.config import Config
from axiom.core.types import AgentStatus

LOGO = """\
 █████╗ ██╗  ██╗██╗ ██████╗ ███╗   ███╗
██╔══██╗╚██╗██╔╝██║██╔═══██╗████╗ ████║
███████║ ╚███╔╝ ██║██║   ██║██╔████╔██║
██╔══██║ ██╔██╗ ██║██║   ██║██║╚██╔╝██║
██║  ██║██╔╝ ██╗██║╚██████╔╝██║ ╚═╝ ██║
╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝     ╚═╝\
"""


class ChatView(VerticalScroll):
    """Scrolling chat/activity view."""

    def append(self, text: Text | str) -> None:
        widget = Static(text, classes="chat-line")
        self.mount(widget)
        self.scroll_end(animate=False)


class AxiomApp(App):
    """Axiom main TUI application."""

    TITLE = "AXIOM"
    CSS = """
    Screen { background: #0d0d10; color: #e6e6ea; }
    #logo { color: #8b1a3a; text-style: bold; padding: 0 1; }
    #status { color: #8a8a92; padding: 0 1; }
    #activity { border: round #2a2a2e; height: 1fr; padding: 0 1; }
    #input { border: round #8b1a3a; }
    Footer { background: #2a2a2e; }
    """
    BINDINGS = [
        ("ctrl+c", "cancel_operation", "Cancel"),
        ("ctrl+l", "clear_screen", "Clear"),
        ("ctrl+n", "new_session", "New session"),
        ("ctrl+p", "model_selector", "Model"),
        ("ctrl+m", "mode_selector", "Mode"),
    ]

    def __init__(self, workspace: Path | None = None, config: Config | None = None) -> None:
        super().__init__()
        self.workspace = workspace or Path.cwd()
        self.config = config or Config(workspace=self.workspace)
        self._agent: Any = None
        self._current_task: asyncio.Task | None = None
        self.mode = "BUILD"

    # -- UI composition ----------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        model_id = self.config.get("model", "model", default="GPT-OSS-120B")
        provider = self.config.get("model", "provider", default="openai_compatible")
        status = Text.assemble(
            (f"{model_id}", "bold"),
            (f" • {self.mode} • {self.workspace}", "dim"),
        )
        yield Static(LOGO, id="logo")
        yield Static(status, id="status")
        yield ChatView(id="activity")
        yield Input(placeholder="Describe a task, or /help for commands…", id="input")
        yield Footer()

    def on_mount(self) -> None:
        view = self.query_one("#activity", ChatView)
        view.append(Text.assemble(("AXIOM ready.", "bold crimson"),
                                  ("  Type a task or /help.", "dim")))
        self.query_one("#input", Input).focus()

    # -- input handling ------------------------------------------------------

    # -- task execution --------------------------------------------------------
    async def _run_task(self, task: str) -> None:
        view = self.query_one("#activity", ChatView)
        try:
            from axiom.agent.agent import Agent
            from axiom.models.manager import ModelManager
        except Exception as exc:  # noqa: BLE001
            view.append(f"[agent unavailable: {exc}]")
            return
        manager = ModelManager(self.config.to_dict())
        current = manager.get_current_model()
        api_key = self.config.get_api_key()
        provider_name = self.config.get("model", "provider", default="openai_compatible")
        provider = manager.create_provider(
            provider_name, model=current.id if current else "GPT-OSS-120B", api_key=api_key
        )
        self._agent = Agent(workspace=self.workspace, config=self.config.to_dict(),
                            provider=provider)
        view.append(Text("◉ Working…", style="bold"))

        def on_event(event_type: str, data: dict[str, Any]) -> None:
            self.call_from_thread(self._on_agent_event, event_type, data)

        self._current_task = asyncio.create_task(
            self._agent.run_task(task, mode=self.mode, on_event=on_event)
        )
        result = await self._current_task
        self._current_task = None
        status_text = (
            "✓ COMPLETE" if result.status == AgentStatus.COMPLETE
            else f"[{result.status.value}]" + (f" {result.error}" if result.error else "")
        )
        view.append(Text.assemble(("Axiom: ", "bold crimson"),
                                  (result.final_text or status_text, "")))
        view.append(Text(f"Status: {result.status.value.upper()} "
                         f"(iters: {result.iterations}, tools: {result.tool_calls})",
                         style="dim"))

    # -- commands -------------------------------------------------------------
    async def handle_command(self, command: str) -> None:
        view = self.query_one("#activity", ChatView)
        parts = command.split(maxsplit=1)
        name = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        if name in ("/exit", "/quit"):
            self.exit()
        elif name == "/help":
            view.append(Text(HELP_TEXT))
        elif name == "/clear":
            self.action_clear_screen()
        elif name == "/project":
            from axiom.tools.project import detect_project

            view.append(Text(detect_project(self.workspace).summary()))
        elif name == "/models":
            self._print_models(view)
        elif name == "/mode":
            self.mode = (arg.upper() or "BUILD")
            self.query_one("#status", Static).update(
                Text(f"{self.config.get('model', 'model')} • {self.mode} • {self.workspace}",
                     style="dim"))
        elif name == "/status":
            info = f"mode: {self.mode}"
            if self._agent is not None:
                info += f", agent mode: {self._agent.mode}"
            view.append(Text(info))
        elif name == "/doctor":
            from axiom.doctor import run_doctor

            report = await run_doctor(self.workspace)
            view.append(Text(report.render()))
        else:
            view.append(Text(f"Unknown command: {name} (try /help)", style="yellow"))

    def _print_models(self, view: ChatView) -> None:
        from axiom.models.manager import ModelManager

        manager = ModelManager(self.config.to_dict())
        for model in manager.list_models():
            view.append(Text(model.id))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        self.query_one("#input", Input).value = ""
        if not value:
            return
        if value.startswith("/"):
            await self.handle_command(value)
            return
        view = self.query_one("#activity", ChatView)
        view.append(Text.assemble(("User: ", "bold"), (value, "")))
        await self._run_task(value)

    def _on_agent_event(self, event_type: str, data: dict[str, Any]) -> None:
        view = self.query_one("#activity", ChatView)
        if event_type == "tool_result":
            mark = "✗" if data.get("is_error") else "├"
            view.append(Text(f"  {mark} {data.get('name', 'tool')}", style="dim"))

    def action_cancel_operation(self) -> None:
        self.exit(return_code=130)

    def action_clear_screen(self) -> None:
        self.query_one("#activity", ChatView).remove_children()

    def action_new_session(self) -> None:
        self.action_clear_screen()
        self.query_one("#activity", ChatView).append(Text("New session.", style="bold"))

    def action_model_selector(self) -> None:
        self.query_one("#activity", ChatView).append(
            Text("Model selector: /models list; /mode <id> hint", style="dim"))

    def action_mode_selector(self) -> None:
        self.query_one("#activity", ChatView).append(
            Text("Modes: PLAN BUILD REVIEW AUTO ORCHESTRATOR — /mode <name>", style="dim"))


HELP_TEXT = """Commands:
  /help  /models  /project  /status  /mode <MODE>  /doctor  /clear  /exit
Shortcuts: Ctrl+C cancel • Ctrl+L clear • Ctrl+N new session • Ctrl+P model • Ctrl+M mode"""


def run_tui(workspace: Path | None = None) -> None:
    """Launch the Axiom TUI."""
    app = AxiomApp(workspace=workspace)
    app.run()
