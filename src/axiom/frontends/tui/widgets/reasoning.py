"""Streaming text blocks and the collapsible reasoning panel.

Nothing here invents content: ``ReasoningPanel`` only exists when the model
really sent reasoning, and its title reflects the real state reported by the
core's state machine.
"""

from __future__ import annotations

from textual.containers import Container
from textual.widgets import Collapsible, Static

from axiom.core.state import GenerationState
from axiom.shared import formatting as fmt
from axiom.shared import theme

#: How often buffered deltas are pushed to the widget (keeps the UI smooth).
FLUSH_INTERVAL = 0.08


class StreamText(Static):
    """A Static that accepts streaming deltas without re-rendering per chunk."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("markup", False)
        super().__init__("", *args, **kwargs)
        self._buffer = ""
        self._rendered = ""

    @property
    def text_content(self) -> str:
        return self._buffer

    def on_mount(self) -> None:
        self.set_interval(FLUSH_INTERVAL, self._flush)

    def append(self, text: str) -> None:
        self._buffer += text

    def set_text(self, text: str) -> None:
        self._buffer = text

    def _flush(self) -> None:
        if self._buffer == self._rendered:
            return
        self._rendered = self._buffer
        self.update(self._buffer)


class ReasoningPanel(Container):
    """Collapsible block holding the model's real reasoning."""

    def __init__(self, *, expanded: bool = False, animations: bool = True) -> None:
        super().__init__(classes="reasoning-panel")
        self._expanded = expanded
        self._animations = animations
        self._tick = 0
        self._state = GenerationState.THINKING.value
        self._active = True
        self._duration_ms: int | None = None
        self._timer = None
        self._pending: list[str] = []

    def compose(self):
        collapsed = not self._expanded
        with Collapsible(
            title=self._title(),
            collapsed=collapsed,
            collapsed_symbol="▸",
            expanded_symbol="▾",
            id="reasoning-collapsible",
        ):
            yield StreamText(id="reasoning-text")

    def on_mount(self) -> None:
        if self._animations:
            self._timer = self.set_interval(theme.SPINNER_INTERVAL, self._animate_title)
        if self._pending:
            # deltas that arrived before the DOM existed (streaming is fast)
            self.query_one("#reasoning-text", StreamText).append("".join(self._pending))
            self._pending.clear()

    # ------------------------------------------------------------------ public

    def append(self, text: str) -> None:
        try:
            stream = self.query_one("#reasoning-text", StreamText)
        except Exception:  # pragma: no cover - composed lazily
            self._pending.append(text)
            return
        stream.append(text)

    def set_state(self, state: GenerationState, *, active: bool) -> None:
        """Track the real state so the title never claims more than it knows."""
        self._state = state.value
        self._active = active
        self._refresh_title()

    def finish(self, state: GenerationState, duration_ms: int | None) -> None:
        self._state = state.value
        self._active = False
        self._duration_ms = duration_ms
        self._refresh_title()
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def toggle(self) -> None:
        collapsible = self.query_one("#reasoning-collapsible", Collapsible)
        collapsible.collapsed = not collapsible.collapsed

    # ----------------------------------------------------------------- private

    def _animate_title(self) -> None:
        if not self._active:
            return
        self._tick += 1
        self._refresh_title()

    def _title(self) -> str:
        label = fmt.status_label(self._state) or "Thinking"
        if self._active and self._state == GenerationState.THINKING.value:
            label = "Thinking"
        if self._active:
            glyph = fmt.spinner_frame(self._tick)
        elif self._state == GenerationState.ERROR.value:
            glyph = theme.CROSS
        else:
            glyph = theme.TICK
        parts = [f"{label} {glyph}"]
        duration = fmt.format_duration_ms(self._duration_ms)
        if duration:
            parts.append(duration)
        return "  ".join(parts)

    def _refresh_title(self) -> None:
        try:
            collapsible = self.query_one("#reasoning-collapsible", Collapsible)
        except Exception:  # pragma: no cover - widget not composed yet
            return
        title = self._title()
        if title != collapsible.title:
            collapsible.title = title