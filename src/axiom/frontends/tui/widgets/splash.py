"""Splash screen — animated logo plus the *real* startup sequence.

Every step reports what actually happened (Ollama reachable or not, how many
models were found, which model was selected). Nothing here fakes progress: a
step is ``◌`` only while its real probe is running.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static

from axiom.shared import formatting as fmt
from axiom.shared import logo as logo_art
from axiom.shared import theme

#: Minimum splash time so the logo animation is actually visible.
MIN_SPLASH_SECONDS = 0.9
#: Vertical bounce pattern (a slow, subtle float).
BOUNCE = (0, 0, 1, 1, 0, 0, -1, -1)


@dataclass
class StartupStep:
    """One real startup probe."""

    title: str
    run: Callable[[], Awaitable[tuple[bool, str]]]


class ActionOption(Static):
    """A minimal clickable/selectable action (Retry / Exit)."""

    class Pressed(Message):
        def __init__(self, label: str) -> None:
            self.label = label
            super().__init__()

    def __init__(self, label: str) -> None:
        super().__init__(label, classes="action", markup=False)
        self.label_text = label

    def on_click(self) -> None:
        self.post_message(self.Pressed(self.label_text))


class SplashScreen(Screen):
    """Logo, tagline, real step list, and Retry/Exit on failure."""

    BINDINGS = [("left", "move(-1)", "Previous"), ("right", "move(1)", "Next")]

    def __init__(self, steps: list[StartupStep], *, animations: bool = True) -> None:
        super().__init__(id="splash-screen")
        self._steps = steps
        self._animations = animations
        self._frame = 0
        self._finished = False
        self._failed_reason: str | None = None
        self._selected = 0
        self._timer = None
        self._actions: list[ActionOption] = []
        self._active_line: Static | None = None
        self._active_title: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-column"):
            yield Static("", id="splash-logo", markup=False)
            yield Static(logo_art.LOGO_RULE, id="splash-rule", markup=False)
            yield Static(logo_art.SUBTITLE, id="splash-subtitle", markup=False)
            yield Vertical(id="splash-steps")
            yield Static("", id="splash-message", markup=False)
            yield Horizontal(id="splash-actions")

    def on_mount(self) -> None:
        self._draw_logo()
        if self._animations:
            self._timer = self.set_interval(0.1, self._animate_splash)
        self.run_worker(self._run_steps, exclusive=True, name="startup")

    # ---------------------------------------------------------------- animation

    def _animate_splash(self) -> None:
        self._frame += 1
        self._draw_logo()
        self._spin_active_step()

    def _spin_active_step(self) -> None:
        """Animate the glyph of the step that is currently running."""
        if self._active_line is None or self._active_title is None:
            return
        self._active_line.update(f"{fmt.spinner_frame(self._frame)}  {self._active_title}")
# -------------------------------------------------------------- step runner

    async def _run_steps(self) -> None:
        started = time.perf_counter()
        container = self.query_one("#splash-steps", Vertical)
        ok_overall = True
        for step in self._steps:
            line = Static(f"{fmt.spinner_frame(0)}  {step.title}", classes="splash-step", markup=False)
            self._active_line = line
            self._active_title = step.title
            await container.mount(line)
            try:
                ok, note = await step.run()
            except Exception as exc:  # noqa: BLE001 - a failed probe must be shown
                ok, note = False, f"{type(exc).__name__}: {exc}"
            self._active_line = None
            self._active_title = None
            glyph = theme.TICK if ok else theme.CROSS
            line.update(f"{glyph}  {step.title}\n     {note}")
            line.set_class(not ok, "failed")
            if not ok:
                ok_overall = False
                self._failed_reason = f"{step.title}: {note}"
                break
        if self._animations:
            remaining = MIN_SPLASH_SECONDS - (time.perf_counter() - started)
            if remaining > 0:
                await asyncio.sleep(remaining)
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
        self._finished = True
        if ok_overall:
            self.query_one("#splash-message", Static).update("Starting AXIOM …")
            # The workspace lives in the app; the splash only asks for it.
            start = getattr(self.app, "start_workspace", None)
            if callable(start):
                start()
        else:
            self._show_failure()

    def _show_failure(self) -> None:
        message = self.query_one("#splash-message", Static)
        message.update(self._failed_reason or "Startup failed.")
        message.set_class(True, "failed")
        actions = self.query_one("#splash-actions", Horizontal)
        self._actions = [ActionOption("Retry"), ActionOption("Exit")]
        self._selected = 0
        actions.mount_all(self._actions)
        self._apply_selection()

    def _apply_selection(self) -> None:
        for index, option in enumerate(self._actions):
            option.set_class(index == self._selected, "selected")

    # -------------------------------------------------------------------- events

    def on_key(self, event: events.Key) -> None:
        if not self._actions:
            return
        if event.key == "left":
            event.stop()
            self._move(-1)
        elif event.key == "right":
            event.stop()
            self._move(1)
        elif event.key == "enter":
            event.stop()
            self._activate(self._actions[self._selected].label_text)

    def _move(self, delta: int) -> None:
        self._selected = (self._selected + delta) % len(self._actions)
        self._apply_selection()

    def on_action_option_pressed(self, event: ActionOption.Pressed) -> None:
        event.stop()
        self._activate(event.label)

    def _activate(self, label: str) -> None:
        if label == "Retry":
            self._retry()
        else:
            self.app.exit()

    def _retry(self) -> None:
        for option in self._actions:
            option.remove()
        self._actions = []
        for child in list(self.query_one("#splash-steps", Vertical).children):
            child.remove()
        message = self.query_one("#splash-message", Static)
        message.update("")
        message.set_class(False, "failed")
        self._finished = False
        self._failed_reason = None
        if self._animations and self._timer is None:
            self._timer = self.set_interval(0.1, self._animate_splash)
        self.run_worker(self._run_steps, exclusive=True, name="startup-retry")

    def _draw_logo(self) -> None:
        width = self.size.width or 80
        offset = BOUNCE[self._frame % len(BOUNCE)]
        lines = logo_art.logo_frame(offset, width)
        centered = "\n".join(f"{line:^{min(width, 80)}}" for line in lines)
        self.query_one("#splash-logo", Static).update(centered)