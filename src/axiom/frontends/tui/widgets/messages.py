"""Message widgets — one container per exchange, driven strictly by core events."""

from __future__ import annotations

from textual.containers import Container, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Markdown, Static
from textual.widgets._markdown import MarkdownStream

from axiom.core.events import SourceItem
from axiom.core.state import GenerationState
from axiom.shared import formatting as fmt
from axiom.shared import theme

from axiom.frontends.tui.widgets.reasoning import ReasoningPanel
from axiom.frontends.tui.widgets.search import WebSearchPanel


class UserMessage(Container):
    """A user turn (never re-rendered once added)."""

    def __init__(self, text: str, timestamp: float | None = None) -> None:
        super().__init__(classes="message user-message")
        self.body = text
        self.timestamp = timestamp

    def compose(self):
        stamp = fmt.format_clock(self.timestamp)
        label = "YOU" + (f"  ·  {stamp}" if stamp else "")
        yield Static(label, classes="role-label")
        yield Static(self.body, classes="message-body", markup=False)


class AssistantMessage(Container):
    """An assistant turn: status, optional reasoning, search, answer, metrics."""

    def __init__(self, *, animations: bool = True, reasoning_expanded: bool = False) -> None:
        super().__init__(classes="message assistant-message")
        self._animations = animations
        self._expanded = reasoning_expanded
        self._tick = 0
        self._state = GenerationState.CONNECTING
        self._active = True
        self._detail: str | None = None
        self._duration_ms: int | None = None
        self._timer = None
        self._reasoning: ReasoningPanel | None = None
        self._search: WebSearchPanel | None = None
        self._error_box: Static | None = None
        self._stream: MarkdownStream | None = None
        self.answering = False
        self.finished = False

    def compose(self):
        yield Static("AXIOM", classes="role-label")
        yield Static("", id="assistant-status", classes="assistant-status")
        yield Static("ANSWER", id="answer-label", classes="block-label")
        yield Markdown("", id="answer-markdown")

    def on_mount(self) -> None:
        self.query_one("#answer-label", Static).display = False
        self.query_one("#answer-markdown", Markdown).display = False
        if self._animations:
            self._timer = self.set_interval(theme.SPINNER_INTERVAL, self._animate_status)
        self._refresh_status()

    # ------------------------------------------------------------------ status

    def set_state(self, state: GenerationState, *, detail: str | None = None) -> None:
        self._state = state
        self._active = state.is_busy
        if detail is not None:
            self._detail = detail
        if self._reasoning is not None:
            self._reasoning.set_state(state, active=state.is_busy)
        self._refresh_status()

    def _animate_status(self) -> None:
        if not self._active:
            return
        self._tick += 1
        self._refresh_status()

    def _refresh_status(self) -> None:
        try:
            widget = self.query_one("#assistant-status", Static)
        except NoMatches:  # pragma: no cover - not composed yet
            return
        if self.finished and self._state == GenerationState.COMPLETED and self.answering:
            widget.display = False
            return
        widget.display = True
        widget.update(
            fmt.status_line(
                self._state.value,
                tick=self._tick,
                duration_ms=self._duration_ms,
                detail=self._detail,
                active=self._active,
            )
        )

    def finish(
        self,
        state: GenerationState,
        *,
        duration_ms: int | None = None,
        tokens_out: int | None = None,
        tokens_per_second: float | None = None,
    ) -> None:
        self._state = state
        self._active = False
        self._duration_ms = duration_ms
        self.finished = True
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._reasoning is not None:
            self._reasoning.finish(state, duration_ms)
        if self._search is not None:
            self._search.finish(cancelled=state == GenerationState.CANCELLED)
        self._refresh_status()
        parts: list[str] = []
        duration = fmt.format_duration_ms(duration_ms)
        if duration:
            parts.append(duration)
        if tokens_out is not None:
            parts.append(f"{fmt.format_tokens(tokens_out)} tok")
        rate = fmt.format_rate(tokens_per_second)
        if rate:
            parts.append(rate)
        if parts:
            self.mount(Static("  ".join(parts), classes="metrics-footer", markup=False))

    # --------------------------------------------------------------- reasoning

    def add_reasoning(self, text: str) -> None:
        if self._reasoning is None:
            self._reasoning = ReasoningPanel(expanded=self._expanded, animations=self._animations)
            self.mount(self._reasoning, before=0)
            self._reasoning.set_state(self._state, active=self._active)
        self._reasoning.append(text)

    @property
    def reasoning_panel(self) -> ReasoningPanel | None:
        return self._reasoning

    # ------------------------------------------------------------------ search

    def _ensure_search(self) -> WebSearchPanel:
        if self._search is None:
            self._search = WebSearchPanel(animations=self._animations)
            self.mount(self._search, before=0)
        return self._search

    def search_started(self, query: str) -> None:
        self._ensure_search().search_started(query)

    def search_finished(self, query: str, sources: list[SourceItem]) -> None:
        self._ensure_search().search_finished(query, sources)

    def search_failed(self, message: str) -> None:
        self._ensure_search().search_failed(message)

    def read_started(self, url: str) -> None:
        self._ensure_search().read_started(url)

    def read_finished(self, url: str, ok: bool) -> None:
        self._ensure_search().read_finished(url, ok)

    # ------------------------------------------------------------------ answer

    def stream(self) -> MarkdownStream:
        if self._stream is None:
            markdown = self.query_one("#answer-markdown", Markdown)
            self._stream = Markdown.get_stream(markdown)
        return self._stream

    async def add_answer(self, text: str) -> None:
        if not text:
            return
        if not self.answering:
            self.answering = True
            self.query_one("#answer-label", Static).display = True
            self.query_one("#answer-markdown", Markdown).display = True
        await self.stream().write(text)

    async def close_stream(self) -> None:
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None

    # ----------------------------------------------------------- errors / notes

    def add_error(self, message: str, hint: str | None = None) -> None:
        text = f"{theme.CROSS} {message}"
        if hint:
            text += f"\n   {hint}"
        self._error_box = Static(text, classes="error-box", markup=False)
        self.mount(self._error_box)

    def add_note(self, text: str) -> None:
        self.mount(Static(text, classes="message-note", markup=False))


class ChatView(VerticalScroll):
    """The conversation area: auto-follows new output unless the user scrolls up."""

    def __init__(self, **kwargs) -> None:
        super().__init__(id="chat-view", **kwargs)
        self._follow = True

    def compose(self):
        yield Static(
            "↓ New output — press End to follow",
            id="follow-hint",
            markup=False,
        )

    def on_mount(self) -> None:
        self.query_one("#follow-hint", Static).display = False

    @property
    def following(self) -> bool:
        return self._follow

    def watch_scroll_y(self, old_value: float | None, new_value: float) -> None:
        """Follow the tail while the user stays at the bottom."""
        if self.max_scroll_y <= 0:
            self._follow = True
        elif new_value >= self.max_scroll_y - 2:
            self._follow = True
        elif old_value is not None and new_value < old_value:
            self._follow = False
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        try:
            hint = self.query_one("#follow-hint", Static)
        except NoMatches:  # pragma: no cover
            return
        hint.display = not self._follow

    def add(self, widget) -> None:
        self.mount(widget)
        self.follow()

    def follow(self) -> None:
        if self._follow:
            self.scroll_end(animate=False)

    def jump_to_end(self) -> None:
        self._follow = True
        self.scroll_end(animate=False)
        self._refresh_hint()

    def clear_messages(self) -> None:
        for child in list(self.children):
            if isinstance(child, (UserMessage, AssistantMessage)):
                child.remove()
        self._follow = True
        self.scroll_home(animate=False)