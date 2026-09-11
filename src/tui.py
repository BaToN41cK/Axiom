"""AXIOM interactive TUI — Textual-based terminal agent interface.

Full-screen application with split layout, live streaming, scrollback,
command palette (Ctrl+P), keyboard navigation and reactive state.
"""

import asyncio
from typing import Optional

from rich.text import Text
from rich.markdown import Markdown as RichMarkdown

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll, Horizontal
from textual.widgets import (
    Static,
    Input,
    Footer,
    TabbedContent,
    TabPane,
    ProgressBar,
    Tree,
)
from textual.command import Provider, Hit, Hits

from src.config import config
from src.session import Session
from src.agent import Agent
from src.ui.tasklog import TaskLog
from src.ui.startup import check_ollama_connection, check_model_available
from src.ollama import OllamaClient

STATE_LABEL = {
    "ready": "● READY",
    "thinking": "◐ THINKING",
    "reasoning": "◐ REASONING",
    "planning": "◐ PLANNING",
    "generating": "● GENERATING",
    "searching": "◐ SEARCHING",
    "researching": "◐ RESEARCHING",
    "offline": "✗ OFFLINE",
}

STEP_EVENTS = {
    "thinking": "Thinking",
    "reasoning": "Reasoning",
    "planning": "Planning",
}

THINKING_PREVIEW = 400


class AxiomCommands(Provider):
    """Command palette commands (Ctrl+P)."""

    @property
    def commands(self) -> list[tuple[str, str, str]]:
        web_state = "disable" if config.web_enabled else "enable"
        think_state = "disable" if config.reasoning_enabled else "enable"
        return [
            ("new session", "start_new_session", "Start a fresh conversation"),
            ("clear conversation", "clear_chat", "Clear the visible conversation"),
            ("change model", "show_models", "List models available in Ollama"),
            (f"{web_state} web tools", "toggle_web", "Toggle web search tools"),
            (f"{think_state} thinking", "toggle_thinking", "Toggle reasoning display"),
            ("toggle sidebar", "toggle_sidebar", "Show or hide the sidebar (Ctrl+B)"),
            ("exit", "quit", "Close AXIOM"),
        ]

    async def search(self, query: str) -> Hits:
        matcher = self.fuzzy_matcher
        for name, action, desc in self.commands:
            score = matcher.match(query, name)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(name),
                    self.app.run_action,
                    action,
                    help=desc,
                )


class AxiomTUI(App):
    """AXIOM interactive terminal AI interface."""

    TITLE = "AXIOM"
    COMMANDS = {AxiomCommands}

    CSS = """
    #topbar { height: 1; background: $surface; padding: 0 1; }
    #main { height: 1fr; }
    #chat {
        width: 1fr;
        padding: 0 1;
        scrollbar-background: $surface;
        scrollbar-color: $primary-darken-1;
    }
    #log { height: auto; }
    #sidebar {
        width: 34;
        min-width: 24;
        border-left: round $primary-darken-1;
        padding: 0 1;
    }
    #sidebar TabPane { padding: 1 1; }
    #ctxbar { margin-bottom: 1; }
    #context_info { color: $text-muted; }
    #stats { height: 1; background: $surface; padding: 0 1; }
    #prompt {
        height: 3;
        border: round $primary-darken-1;
        padding: 0 1;
    }
    #prompt:focus { border: round $success; }
    Footer { background: $surface; }
    """

    BINDINGS = [
        ("ctrl+c", "cancel_or_quit", "Cancel/Quit"),
        ("ctrl+l", "clear_chat", "Clear"),
        ("ctrl+b", "toggle_sidebar", "Sidebar"),
        ("escape", "cancel_generation", "Cancel"),
    ]

    # Reactive state
    state: str = "offline"
    busy: bool = False

    def __init__(self, model: str = ""):
        super().__init__()
        self.model_name = model or config.model
        self.session = Session()
        self.agent: Optional[Agent] = None
        self.ollama = OllamaClient(model=self.model_name)
        self.tasklog = TaskLog()
        self._stream_widget: Optional[Static] = None
        self._think_widget: Optional[Static] = None
        self._answer_text = ""
        self._thinking_text = ""

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="main"):
            with VerticalScroll(id="chat"):
                yield Vertical(id="log")
            with TabbedContent(id="sidebar"):
                with TabPane("WORKFLOW"):
                    yield Static(id="workflow")
                with TabPane("SESSION"):
                    yield Tree("AXIOM", id="session_tree")
                with TabPane("CONTEXT"):
                    yield ProgressBar(id="ctxbar", total=100, show_eta=False,
                                      show_percentage=True)
                    yield Static(id="context_info")
        yield Static(id="stats")
        yield Input(placeholder="Ask AXIOM anything...", id="prompt")
        yield Footer()

    def on_mount(self):
        """Start initialization checks."""
        self.query_one("#prompt", Input).focus()
        self._refresh_topbar()
        self._refresh_stats()
        self._log_line("Initializing AXIOM...", "dim")
        self.run_worker(self._initialize(), exclusive=True)

    async def _initialize(self):
        """Check Ollama and model availability."""
        ok, msg = await check_ollama_connection()
        if not ok:
            self._set_state("offline")
            self._log_line(
                f"✗ Cannot connect to Ollama ({msg}). Start Ollama and restart AXIOM.",
                "bold red",
            )
            self.notify("Ollama is not reachable", severity="error", timeout=10)
            return

        model_ok, _msg, _models = await check_model_available()
        if not model_ok:
            self._set_state("offline")
            self._log_line(
                f"✗ Model '{self.model_name}' is not installed.\n"
                f"  Run: ollama pull {self.model_name}",
                "bold red",
            )
            self.notify(
                f"Model {self.model_name} not found", severity="error", timeout=10)
            return

        self.agent = Agent(self.session, self.model_name)
        self._set_state("ready")
        self._log_line(f"✓ Ollama connected — {self.model_name} ready", "bold green")
        self._log_line("Ctrl+P — commands │ Esc — cancel generation", "dim")

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    @property
    # -- Actions -------------------------------------------------------------

    async def action_cancel_or_quit(self):
        """Ctrl+C: abort generation if running, otherwise quit."""
        if self.busy:
            await self.action_cancel_generation()
        else:
            self.exit()

    async def action_cancel_generation(self):
        """Abort the current generation."""
        if self.agent is not None and self.busy:
            self.notify("Generation cancelled", severity="warning", timeout=4)
            self.agent.cancel()

    async def action_toggle_sidebar(self):
        """Ctrl+B — show or hide the right sidebar."""
        sidebar = self.query_one("#sidebar", TabbedContent)
        sidebar.display = not sidebar.display

    async def action_clear_chat(self):
        """Clear the visible conversation log."""
        log = self.query_one("#log", Vertical)
        log.remove_children()
        self._welcome()

    async def action_start_new_session(self):
        """Start a fresh agent session."""
        self.session = Session()
        if self.agent is not None:
            self.agent = Agent(self.session, model=self.model_name)
        await self.action_clear_chat()
        self._log_line("✓ New session started", "bold green")

    async def action_show_models(self):
        """List models available in Ollama."""
        if self.agent is None:
            self._log_line("Not connected.", "bold red")
            return
        try:
            models = await self.agent.ollama.list_models()
        except Exception as e:
            self._log_line(f"Failed to fetch models: {e}", "bold red")
            return
        text = Text("Models in Ollama\n", style="bold")
        for m in models:
            name = m.get("name", "?")
            marker = "●" if name == self.model_name else "○"
            text.append(f"  {marker} {name}\n",
                        style="green" if name == self.model_name else "dim")
        self._log_rich(text)

    async def action_toggle_web(self):
        """Toggle web tools."""
        config.web_enabled = not config.web_enabled
        state = "enabled" if config.web_enabled else "disabled"
        self._log_line(f"✓ Web tools {state}", "bold green")
        self._refresh_topbar()

    async def action_toggle_thinking(self):
        """Toggle reasoning display."""
        config.reasoning_enabled = not config.reasoning_enabled
        state = "enabled" if config.reasoning_enabled else "disabled"
        self._log_line(f"✓ Thinking {state}", "bold green")
        self._refresh_topbar()

    def _welcome(self):
        """Show the welcome hint after start or clear."""
        self._log_line("Welcome to AXIOM — local AI terminal.", "dim")
        self._log_line(
            "Ctrl+P commands │ Ctrl+L clear │ Esc cancel │ /help", "dim")

    # -- Live event handlers -------------------------------------------------

    @property
    def chat_log(self) -> Vertical:
        """The conversation log container."""
        return self.query_one("#log", Vertical)

    def _scroll_end(self):
        self.query_one("#chat", VerticalScroll).scroll_end(animate=False)

    def _log_line(self, text: str, style: str = ""):
        """Append a simple text line to the conversation log."""
        line = Static(Text(text, style=style))
        line.can_focus = False
        self.chat_log.mount(line)
        self._scroll_end()

    def _log_rich(self, renderable) -> Static:
        """Append any rich renderable to the conversation log."""
        widget = Static(renderable)
        widget.can_focus = False
        self.chat_log.mount(widget)
        self._scroll_end()
        return widget

    def _refresh_topbar(self):
        bar = self.query_one("#topbar", Static)
        state_style = {
            "ready": "bold green",
            "offline": "bold red",
        }.get(self.state, "bold yellow")
        label = STATE_LABEL.get(self.state, "● READY")
        bar.update(Text.assemble(
            ("◈ AXIOM", "bold green"),
            (f"   {self.model_name}", ""),
            (f"   {label}", state_style),
        ))

    def _refresh_stats(self):
        stats = self.query_one("#stats", Static)
        tokens = self.session.formatted_tokens if self.session.total_tokens else "—"
        state_style = {
            "ready": "bold green",
            "offline": "bold red",
        }.get(self.state, "bold yellow")
        label = STATE_LABEL.get(self.state, "● READY")
        stats.update(Text.assemble(
            (f" SEARCH {self.session.total_searches}", "dim"),
            (f" │ TOKENS {tokens}", "dim"),
            (f" │ CONTEXT {self.session.context_percentage}%", "dim"),
            (f" │ TOOLS {self.session.total_tools}", "dim"),
            (f"   {label}", state_style),
        ))
        self._refresh_sidebar()

    def _refresh_sidebar(self):
        """Update the tabbed sidebar: workflow, session tree, context."""
        try:
            self.query_one("#workflow", Static).update(self.tasklog.render())
        except Exception:
            pass

        try:
            tree = self.query_one("#session_tree", Tree)
            tree.clear()
            tree.root.expand()
            tree.root.add_leaf(f"model      {self.model_name}")
            tree.root.add_leaf(f"state      {STATE_LABEL.get(self.state, '?')}")
            tree.root.add_leaf(f"web        {'on' if config.web_enabled else 'off'}")
            tree.root.add_leaf(f"thinking   {'on' if config.reasoning_enabled else 'off'}")
            tree.root.add_leaf(f"messages   {len(self.session.messages)}")
            tree.root.add_leaf(f"searches   {self.session.total_searches}")
            tree.root.add_leaf(f"tools      {self.session.total_tools}")
        except Exception:
            pass

        try:
            bar = self.query_one("#ctxbar", ProgressBar)
            bar.update(progress=self.session.context_percentage)
            used = self.session.total_tokens
            limit = config.context_window
            info = self.query_one("#context_info", Static)
            if used:
                info.update(f"tokens  {used:,} / {limit:,}")
            else:
                info.update(f"tokens  — / {limit:,}")
        except Exception:
            pass

    def _set_state(self, state: str):
        self.state = state
        self._refresh_topbar()
        self._refresh_stats()

    # ------------------------------------------------------------------
    # Agent event callbacks (run inside the event loop)
    # ------------------------------------------------------------------

    def _on_status(self, event: str, started: bool):
        if event == "generating":
            self._set_state("generating" if started else "ready")
            return
        name = STEP_EVENTS.get(event)
        if name is None:
            return
        if started:
            self.tasklog.start(name)
            self._set_state(event)
        else:
            self.tasklog.complete(name)
        self._render_steps()

    def _on_token(self, token: str, is_thinking: bool = False):
        if is_thinking:
            self._thinking_text += token
            if self._think_widget is None:
                self._think_widget = self._log_rich(Text("", style="dim italic"))
            total = self._thinking_text
            shown = ("…" if len(total) > THINKING_PREVIEW else "") + \
                total[-THINKING_PREVIEW:]
            self._think_widget.update(Text(shown, style="dim italic"))
        else:
            self._answer_text += token
            if self._stream_widget is None:
                self._stream_widget = self._log_rich(Text(""))
            self._stream_widget.update(Text(self._answer_text))
        self._scroll_end()

    def _on_tool(self, name: str, args: dict, started: bool, result: Optional[dict] = None):
        if name == "web_search":
            if started:
                query = args.get("query", "") if isinstance(args, dict) else ""
                self.tasklog.start(
                    "Search", f"Searching for “{query}”..." if query else "")
                self._set_state("searching")
            elif isinstance(result, dict) and result.get("error"):
                self.tasklog.fail("Search", "failed")
            else:
                count = result.get("count", 0) if isinstance(result, dict) else 0
                self.tasklog.complete("Search", f"{count} results")
        elif name == "web_fetch":
            if started:
                self.tasklog.start("Web Research", "Reading relevant sources...")
                self._set_state("researching")
            elif isinstance(result, dict) and result.get("error"):
                self.tasklog.fail("Web Research", "failed")
            else:
                self.tasklog.complete(
                    "Web Research", f"{self.agent.status.source_count} sources")
        self._render_steps()

    def _render_steps(self):
        """Re-render the task journal inside the conversation."""
        for widget in list(self.chat_log.children):
            if getattr(widget, "is_step_block", False):
                widget.remove()
        if self.tasklog.steps:
            widget = Static(self.tasklog.render())
            widget.can_focus = False
            widget.is_step_block = True
            self.chat_log.mount(widget)
        self._scroll_end()

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    @on(Input.Submitted, "#prompt")
    async def submit_prompt(self, event: Input.Submitted):
        text = event.value.strip()
        event.input.clear()
        if not text:
            return
        if text.startswith("/"):
            await self._handle_slash(text)
            return
        if self.busy:
            self.notify("AXIOM is busy — Esc to cancel", severity="warning")
            return
        await self._run_generation(text)

    async def _handle_slash(self, text: str):
        cmd = text.lower()
        if cmd in ("/exit", "/quit", "/q"):
            self.exit()
        elif cmd == "/clear":
            self.run_action("clear_chat")
        elif cmd == "/new":
            self.run_action("start_new_session")
        elif cmd == "/web":
            self.run_action("toggle_web")
        elif cmd == "/thinking":
            self.run_action("toggle_thinking")
        elif cmd == "/model":
            self._log_line(f"Model: {self.model_name}", "bold")
        elif cmd == "/models":
            await self.action_show_models()
        elif cmd == "/status":
            self._log_line(
                f"Ollama ● Connected │ Model {self.model_name} │ "
                f"Web {'on' if config.web_enabled else 'off'} │ "
                f"Thinking {'on' if config.reasoning_enabled else 'off'}",
                "dim",
            )
        elif cmd == "/help":
            self._log_line(
                "/help /status /model /models /clear /new /thinking /web /exit",
                "dim",
            )
        else:
            self._log_line(f"Unknown command: {text}", "bold red")

    async def _run_generation(self, message: str):
        """Run the agent for one user message."""
        if self.agent is None:
            self._log_line("Not connected — start Ollama and restart.", "bold red")
            return

        self.busy = True
        self.tasklog = TaskLog()
        self._answer_text = ""
        self._thinking_text = ""
        self._stream_widget = None
        self._think_widget = None

        self._log_line("You", "bold")
        self._log_line(message, "")
        self._log_line("AXIOM", "bold cyan")

        async def work() -> dict:
            try:
                return await self.agent.process_message(
                    message,
                    on_token=self._on_token,
                    on_status=self._on_status,
                    on_tool=self._on_tool,
                )
            except Exception as e:
                return {"success": False, "cancelled": False,
                        "content": "", "error": str(e)}

        result = {}
        try:
            result = await self.run_worker(work(), exclusive=True).wait()
        except Exception:
            pass

        self.busy = False
        self._set_state("ready")
        self._render_steps()

        if result.get("cancelled"):
            self.tasklog.cancel_active()
            self._render_steps()
            self._log_line("⚠ Cancelled", "bold yellow")
            return

        content = result.get("content", "")
        if result.get("success") and content:
            # Replace plain streaming text with rendered markdown.
            if self._stream_widget is not None:
                self._stream_widget.update(RichMarkdown(content))
            else:
                self._log_rich(RichMarkdown(content))

            sources = self.agent.web.results
            if sources:
                lines = Text("\nSources\n", style="bold")
                for i, src in enumerate(sources[:config.max_sources_display], 1):
                    title = src.get("title", "Untitled")
                    lines.append(f"[{i}] {title}\n", style="dim")
                self._log_rich(lines)

            self._log_line("✓ Answer completed", "bold green")
        else:
            self._log_line(
                f"✗ Task failed: {result.get('error', 'unknown')}", "bold red")

        self._refresh_stats()


def main():
    """Entry point for the AXIOM interactive TUI."""
    AxiomTUI().run()


if __name__ == "__main__":
    main()
