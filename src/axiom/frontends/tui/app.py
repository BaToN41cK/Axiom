"""AXIOM TUI application — a thin adapter wiring the core stream to widgets.

The app owns no logic of its own: every status, every reasoning delta and every
source comes from :class:`axiom.core.chat.ChatSession`, and every user action is
routed back into the core (``send`` / ``cancel`` / ``switch_model`` / ...).
"""

from __future__ import annotations

import time
import webbrowser

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.theme import Theme as TextualTheme

from axiom.core.chat import ChatSession, StartupReport
from axiom.core.events import (
    ChatEvent,
    ContentChunk,
    Done,
    ErrorEvent,
    ReasoningChunk,
    SearchResultEvent,
    SourceItem,
    StatusChange,
    ToolResultEvent,
)
from axiom.core.models import ModelRegistry
from axiom.core.state import GenerationState
from axiom.core.tools.web_search import FETCH_URL_TOOL, WEB_SEARCH_TOOL
from axiom.shared import theme as palette

from axiom.frontends.tui.widgets.commands import COMMANDS, find_command
from axiom.frontends.tui.widgets.header import HeaderBar, StatusBar
from axiom.frontends.tui.widgets.messages import AssistantMessage, ChatView, UserMessage
from axiom.frontends.tui.widgets.panels import (
    HelpPanel,
    HistoryPanel,
    ModelPanel,
    SettingsPanel,
    StatusPanel,
)
from axiom.frontends.tui.widgets.prompt import InputBar
from axiom.frontends.tui.widgets.splash import SplashScreen, StartupStep


class WorkspaceScreen(Screen):
    """The main screen: header, chat view, prompt bar and status bar."""

    BINDINGS = [
        Binding("ctrl+c", "stop_generation", "Stop", priority=True),
    ]

    def __init__(
        self,
        session: ChatSession,
        *,
        animations: bool = True,
        version: str | None = None,
    ) -> None:
        super().__init__()
        self.session = session
        self._animations = animations
        self._version = version
        self._generating = False
        self._read_queue: list[SourceItem] = []
        self._read_index = 0

    def compose(self) -> ComposeResult:
        yield HeaderBar()
        yield ChatView()
        yield InputBar()
        yield StatusBar()

    def on_mount(self) -> None:
        self._refresh_model_display()
        # The splash probe already established reachability; reflect its real
        # result here — the status bar keeps updating from live events only.
        connected = self._version is not None
        self.query_one(HeaderBar).set_connection(connected, self._version)
        self.status_bar.set_connection(connected, self._version)
        self.input_bar.input.focus()

    # ------------------------------------------------------------------ helpers

    @property
    def chat_view(self) -> ChatView:
        return self.query_one(ChatView)

    @property
    def input_bar(self) -> InputBar:
        return self.query_one(InputBar)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one(StatusBar)

    def apply_startup(self, report: StartupReport) -> None:
        """Adopt the real splash results (version, model, connection)."""
        if report.version:
            self._version = report.version
        connected = report.ollama_available
        self.query_one(HeaderBar).set_connection(connected, report.version)
        self.status_bar.set_connection(connected, report.version)
        self._refresh_model_display()

    def _refresh_model_display(self) -> None:
        model = self.session.active_model
        display = model.display_name if model is not None else ""
        self.query_one(HeaderBar).update_model(display)
        self.status_bar.set_model(display)

    # --------------------------------------------------------------- generation

    def handle_submit(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if text.startswith("/"):
            self.input_bar.clear_prompt()
            self._execute_command(text)
            return
        self.input_bar.clear_prompt()
        self._start_generation(text)

    def _start_generation(
        self,
        text: str,
        *,
        force_search: bool = False,
        search_query: str | None = None,
    ) -> None:
        if self._generating or self.session.busy:
            self.notify("A generation is already running.", severity="warning", timeout=4)
            return
        self.run_worker(
            self._generate(text, force_search=force_search, search_query=search_query),
            exclusive=True,
            group="generation",
        )

    async def _generate(
        self,
        text: str,
        *,
        force_search: bool = False,
        search_query: str | None = None,
    ) -> None:
        config = self.session.config
        self.chat_view.add(UserMessage(text, time.time()))
        assistant = AssistantMessage(
            animations=self._animations,
            reasoning_expanded=config.reasoning_expanded,
        )
        self.chat_view.add(assistant)
        self._generating = True
        self._read_queue = []
        self._read_index = 0
        self.input_bar.set_busy(True)
        try:
            async for event in self.session.send(
                text, force_search=force_search, search_query=search_query
            ):
                await self._dispatch_event(assistant, event)
        finally:
            self._generating = False
            self.input_bar.set_busy(False)
            await assistant.close_stream()
            if not assistant.finished:
                assistant.finish(GenerationState.ERROR)
            self.status_bar.set_state(self.session.state)
            self.input_bar.input.focus()

    async def _dispatch_event(self, assistant: AssistantMessage, event: ChatEvent) -> None:
        """Project one real core event onto the widgets. No invention here."""
        if isinstance(event, StatusChange):
            assistant.set_state(event.state, detail=event.detail)
            self.status_bar.set_state(event.state, event.detail)
            if event.detail == "read_source":
                self._begin_source_read(assistant)
        elif isinstance(event, ReasoningChunk):
            assistant.add_reasoning(event.text)
        elif isinstance(event, ContentChunk):
            await assistant.add_answer(event.text)
        elif isinstance(event, SearchResultEvent):
            self._read_queue = list(event.sources)
            self._read_index = 0
            assistant.search_finished(event.query, event.sources)
        elif isinstance(event, ToolResultEvent):
            if event.name == WEB_SEARCH_TOOL and not event.ok:
                assistant.search_failed(event.error or "Web search failed.")
            elif event.name == FETCH_URL_TOOL:
                self._end_source_read(assistant, event.ok)
        elif isinstance(event, ErrorEvent):
            assistant.add_error(event.message, event.hint)
        elif isinstance(event, Done):
            await assistant.close_stream()
            assistant.finish(
                event.state,
                duration_ms=event.duration_ms or None,
                tokens_out=event.tokens_out,
                tokens_per_second=event.tokens_per_second,
            )
            self.status_bar.set_state(event.state)
            self.status_bar.add_tokens(event.tokens_out, event.tokens_per_second)
        # ToolCallEvent: the status line already reflects real tool activity.

    def _begin_source_read(self, assistant: AssistantMessage) -> None:
        if self._read_index < len(self._read_queue):
            assistant.read_started(self._read_queue[self._read_index].url)

    def _end_source_read(self, assistant: AssistantMessage, ok: bool) -> None:
        if self._read_index < len(self._read_queue):
            source = self._read_queue[self._read_index]
            self._read_index += 1
            assistant.read_finished(source.url, ok)

    async def action_stop_generation(self) -> None:
        self._request_stop()

    def _request_stop(self) -> None:
        self.session.cancel()

    def on_input_bar_stop_requested(self, event: InputBar.StopRequested) -> None:
        event.stop()
        self._request_stop()

    def on_axiom_input_submitted(self, event) -> None:
        event.stop()
        self.handle_submit(event.value)

    def check_action(self, action: str, parameters: tuple) -> bool:  # type: ignore[override]
        # Ctrl+C only acts as Stop while a generation is really in flight;
        # otherwise the system binding (copy / quit hint) stays intact.
        if action == "stop_generation":
            return self._generating
        return True

    # ------------------------------------------------------------ source clicks

    def on_source_row_opened(self, event) -> None:
        event.stop()
        webbrowser.open(event.source.url)

    def on_key(self, event) -> None:
        if event.key == "end" and not self.input_bar.input.has_focus:
            self.chat_view.jump_to_end()

    # ---------------------------------------------------------------- commands

    def _execute_command(self, raw: str) -> None:
        token, _, argument = raw.strip().partition(" ")
        argument = argument.strip()
        command = find_command(token)
        if command is None:
            self.notify(f"Unknown command: {token}", severity="warning", timeout=4)
            return
        name = command.name
        if name == "/exit":
            self.app.exit()
        elif name == "/help":
            self.app.push_screen(HelpPanel(COMMANDS))
        elif name in ("/model", "/models"):
            if name == "/model" and argument:
                self.run_worker(self._switch_model(argument), exclusive=True, group="model")
            else:
                self.app.push_screen(
                    ModelPanel(
                        self.session.registry.models,
                        self.session.active_model.name if self.session.active_model else None,
                        refresh=self.session.refresh_models,
                    ),
                    callback=self._model_chosen,
                )
        elif name in ("/clear", "/new"):
            self.session.new_conversation()
            self.chat_view.clear_messages()
        elif name == "/history":
            self.app.push_screen(
                HistoryPanel(self.session.history(), on_delete=self._delete_conversation),
                callback=self._history_chosen,
            )
        elif name == "/settings":
            self.app.push_screen(SettingsPanel(self.session.config))
        elif name == "/search":
            if not argument:
                self.notify("Usage: /search <query>", severity="warning", timeout=4)
                return
            self._start_generation(argument, force_search=True, search_query=argument)
        elif name == "/status":
            self.app.push_screen(
                StatusPanel(
                    ollama_url=self.session.client.base_url,
                    version=self._version,
                    model=self.session.active_model,
                    metrics=self.session.last_metrics,
                )
            )

    # ------------------------------------------------------------------ panels

    def _model_chosen(self, name: str | None) -> None:
        if name:
            self.run_worker(self._switch_model(name), exclusive=True, group="model")

    async def _switch_model(self, name: str) -> None:
        try:
            model = await self.session.switch_model(name)
        except Exception as exc:  # noqa: BLE001 - surfaced as a clean notice
            self.notify(str(exc), severity="error", timeout=6)
            return
        self._refresh_model_display()
        self.notify(f"Model switched to {model.display_name}", title="Models", timeout=4)

    def _history_chosen(self, conversation_id: str | None) -> None:
        if not conversation_id:
            return
        conversation = self.session.load_conversation(conversation_id)
        if conversation is None:
            self.notify("Could not open that conversation.", severity="error", timeout=6)
            return
        self._render_conversation(conversation)

    def _delete_conversation(self, conversation_id: str) -> bool:
        return self.session.delete_conversation(conversation_id)

    def _render_conversation(self, conversation) -> None:
        """Project a stored conversation back onto the chat view."""
        self.chat_view.clear_messages()
        for message in conversation.messages:
            if message.role == "user" and message.content:
                self.chat_view.add(UserMessage(message.content, message.created_at))
            elif message.role == "assistant" and (message.content or message.thinking):
                assistant = AssistantMessage(
                    animations=self._animations,
                    reasoning_expanded=self.session.config.reasoning_expanded,
                )
                self.chat_view.add(assistant)
                self.run_worker(
                    self._render_stored_answer(assistant, message.content, message.thinking),
                    exclusive=False,
                    group="render",
                )

    async def _render_stored_answer(
        self, assistant: AssistantMessage, content: str, thinking: str | None
    ) -> None:
        if thinking:
            assistant.add_reasoning(thinking)
        if content:
            await assistant.add_answer(content)
        if assistant.reasoning_panel is not None:
            assistant.reasoning_panel.finish(GenerationState.COMPLETED, None)
        assistant.finish(GenerationState.COMPLETED)


class AxiomApp(App):
    """AXIOM workspace: real startup probes, then the main screen."""

    CSS_PATH = "theme.tcss"
    TITLE = "AXIOM"

    def __init__(self, session: ChatSession | None = None) -> None:
        super().__init__()
        self.session = session or ChatSession()
        self._version: str | None = None

    def on_mount(self) -> None:
        self.register_theme(TextualTheme(**palette.THEME_COLORS))
        self.theme = palette.THEME_NAME
        self.push_screen(
            SplashScreen(self._startup_steps(), animations=self.session.config.animations)
        )

    # ------------------------------------------------------------ real startup

    def _startup_steps(self) -> list[StartupStep]:
        session = self.session

        async def connect() -> tuple[bool, str]:
            if not await session.client.is_available():
                return False, f"Ollama is not reachable at {session.client.base_url}"
            version = await session.client.version()
            self._version = version
            return True, f"Ollama {version}"

        async def detect_models() -> tuple[bool, str]:
            models = await session.registry.refresh()
            if not models:
                return False, "No models are installed. Run: ollama pull qwen3:8b"
            return True, f"{len(models)} model(s) detected"

        async def select_model() -> tuple[bool, str]:
            model = session.registry.resolve(session.config.model)
            if model is None:
                return False, "No model is available"
            session.active_model = model
            session.conversation.model = model.name
            ModelRegistry.persist_selection(session.config, model.name)
            return True, model.display_name

        async def init_workspace() -> tuple[bool, str]:
            session.config.save()
            return True, "Workspace ready"

        return [
            StartupStep("Connecting to Ollama", connect),
            StartupStep("Detecting models", detect_models),
            StartupStep("Selecting model", select_model),
            StartupStep("Initializing workspace", init_workspace),
        ]

    def start_workspace(self) -> None:
        """Switch from the splash to the main screen (called by SplashScreen)."""
        self.pop_screen()
        self.push_screen(
            WorkspaceScreen(
                self.session,
                animations=self.session.config.animations,
                version=self._version,
            )
        )


def main() -> int:
    """Entry point used by ``axiom.__main__``."""
    session = ChatSession()
    app = AxiomApp(session)
    app.run()
    return 0
