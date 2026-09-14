"""Input bar — multiline prompt, slash completion and a real Stop control."""

from __future__ import annotations

from textual import events
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import OptionList, Static, TextArea

from axiom.shared import theme

from axiom.frontends.tui.widgets.commands import Command, CommandMenu

HINT_IDLE = "Enter send   ·   Ctrl+J newline   ·   / commands   ·   Ctrl+Q quit"
HINT_BUSY = "Ctrl+C stop   ·   Esc dismiss"


class AxiomInput(TextArea):
    """Multiline prompt: Enter sends, Ctrl+J / Alt+Enter break the line."""

    class Submitted(Message):
        """Enter was pressed on a non-empty prompt."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "",
            id="prompt-input",
            soft_wrap=True,
            show_line_numbers=False,
            highlight_cursor_line=False,
            tab_behavior="focus",
            theme="css",
            **kwargs,
        )

    async def _on_key(self, event: events.Key) -> None:  # noqa: D401 - documented above
        # TextArea consumes Enter internally, so it must be intercepted here.
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self.text))
            return
        if event.key in ("ctrl+j", "alt+enter", "shift+enter", "ctrl+enter"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        await super()._on_key(event)

    def set_prompt(self, value: str) -> None:
        """Replace the whole prompt (used by command completion)."""
        self.clear()
        if value:
            self.insert(value)
        self.focus()


class StopButton(Static):
    """Clickable stop control, shown only while a generation is in flight."""

    class Pressed(Message):
        """The button was clicked."""

    def __init__(self) -> None:
        super().__init__("Stop", id="stop-button", markup=False)

    def on_click(self) -> None:
        self.post_message(self.Pressed())


class InputBar(Container):
    """Prompt glyph + text area + Stop button + contextual hint line."""

    class StopRequested(Message):
        """The Stop control was activated."""

    def compose(self):
        yield CommandMenu()
        with Horizontal(id="prompt-row"):
            yield Static(theme.PROMPT_GLYPH, id="prompt-glyph")
            yield AxiomInput()
            yield StopButton()
        yield Static(HINT_IDLE, id="input-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one(StopButton).display = False

    # ------------------------------------------------------------------ helpers

    @property
    def input(self) -> AxiomInput:
        return self.query_one(AxiomInput)

    def value(self) -> str:
        return self.input.text

    def clear_prompt(self) -> None:
        self.input.clear()
        self.query_one(CommandMenu).hide()

    def set_busy(self, busy: bool) -> None:
        self.query_one(StopButton).display = busy
        self.query_one("#prompt-glyph", Static).set_class(busy, "busy")
        self.query_one("#input-hint", Static).update(HINT_BUSY if busy else HINT_IDLE)

    def complete(self, command: Command) -> None:
        """Insert the highlighted command and keep the caret ready for arguments."""
        value = command.usage
        if command.argument_hint:
            value += " "
        self.input.set_prompt(value)
        self.query_one(CommandMenu).hide()

    # -------------------------------------------------------------------- events

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area is self.input:
            self.query_one(CommandMenu).show_for(event.text_area.text)

    def on_axiom_input_submitted(self, event: AxiomInput.Submitted) -> None:
        """Use Enter as command completion while the menu is open."""
        menu = self.query_one(CommandMenu)
        command = menu.highlighted_command() if menu.open else None
        if command is not None:
            event.stop()
            self.complete(command)

    def on_key(self, event: events.Key) -> None:
        menu = self.query_one(CommandMenu)
        option_list = self.query_one("#command-menu-list", OptionList)
        if event.key == "tab" and menu.open:
            command = menu.highlighted_command()
            if command is not None:
                event.stop()
                event.prevent_default()
                self.complete(command)
        elif event.key == "escape" and menu.open:
            event.stop()
            self.query_one(CommandMenu).hide()
        elif event.key == "down" and menu.open:
            # arrows navigate the command menu while the caret stays in the input
            event.stop()
            event.prevent_default()
            option_list.action_cursor_down()
        elif event.key == "up" and menu.open:
            event.stop()
            event.prevent_default()
            option_list.action_cursor_up()

    def on_click(self, event) -> None:
        widget = event.widget if hasattr(event, "widget") else None
        if isinstance(widget, Static) and widget.id == "stop-button":
            self.post_message(self.StopRequested())

    def on_stop_button_pressed(self, event: StopButton.Pressed) -> None:
        event.stop()
        self.post_message(self.StopRequested())

    def on_command_menu_chosen(self, event: CommandMenu.Chosen) -> None:
        event.stop()
        self.complete(event.command)