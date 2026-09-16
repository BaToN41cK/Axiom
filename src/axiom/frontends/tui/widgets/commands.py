"""Slash commands — registry data plus the autocomplete menu widget.

The command list is data (name, usage, description); the actions themselves live
in :mod:`axiom.frontends.tui.app`, where they are wired to real core calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from axiom.shared import theme


@dataclass(frozen=True)
class Command:
    """One slash command."""

    name: str
    description: str
    argument_hint: str = ""

    @property
    def usage(self) -> str:
        return f"{self.name} {self.argument_hint}".strip()


#: Canonical command set (OpenCode-style).
COMMANDS: tuple[Command, ...] = (
    Command("/help", "Show help"),
    Command("/model", "Change model", "[name]"),
    Command("/models", "Model list"),
    Command("/clear", "Clear conversation"),
    Command("/history", "Conversation history"),
    Command("/new", "New conversation"),
    Command("/settings", "Settings"),
    Command("/search", "Web search", "query"),
    Command("/status", "System status"),
    Command("/exit", "Exit Axiom"),
)

_COMMAND_INDEX = {command.name: command for command in COMMANDS}


def find_command(token: str) -> Command | None:
    """Resolve ``/mo`` style tokens to a real command (exact name first)."""
    token = token.strip().split()[0] if token.strip() else ""
    if token in _COMMAND_INDEX:
        return _COMMAND_INDEX[token]
    matches = matching_commands(token)
    if len(matches) == 1:
        return matches[0]
    return None


def matching_commands(prefix: str) -> list[Command]:
    """Filter commands by the text typed after ``/`` (fuzzy on name)."""
    prefix = prefix.lstrip("/").lower()
    if not prefix:
        return list(COMMANDS)
    exact = [c for c in COMMANDS if c.name[1:] == prefix]
    if exact:
        return exact
    starts = [c for c in COMMANDS if c.name[1:].startswith(prefix)]
    if starts:
        return starts
    return [c for c in COMMANDS if prefix in c.name[1:]]


def command_rows(commands: list[Command], width: int = 60) -> list[Option]:
    """Render commands as option rows, aligned for the menu panel."""
    widest = max((len(c.usage) for c in commands), default=8)
    widest = min(widest, max(10, width - 24))
    rows: list[Option] = []
    for command in commands:
        usage = command.usage.ljust(widest)
        rows.append(Option(f"{usage}  {command.description}", id=command.name))
    return rows


class CommandMenu(Vertical):
    """The ``/`` autocomplete panel — filtered, arrow-navigable, mouse-clickable."""

    class Chosen(Message):
        """A command was accepted (Enter, Tab or click)."""

        def __init__(self, command: Command) -> None:
            self.command = command
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(id="command-menu", **kwargs)
        self._visible = False

    def compose(self):
        yield Static("COMMANDS", id="command-menu-title")
        yield OptionList(id="command-menu-list")

    @property
    def open(self) -> bool:
        return self._visible

    def on_mount(self) -> None:
        self.display = False

    def show_for(self, text: str) -> None:
        """Open the menu and filter it for the current input text."""
        if not text.startswith("/"):
            self.hide()
            return
        token = text.split(" ", 1)[0]
        # once a space is typed the command itself is settled: hide the menu
        argument_typed = " " in text.strip()
        commands = matching_commands(token)
        if argument_typed:
            self.hide()
            return
        if not commands:
            self.hide()
            return
        option_list = self.query_one("#command-menu-list", OptionList)
        option_list.clear_options()
        for option in command_rows(commands, self.size.width or 60):
            option_list.add_option(option)
        option_list.highlighted = 0
        self._visible = True
        self.display = True
        self.refresh(layout=True)

    def hide(self) -> None:
        if not self._visible:
            return
        self._visible = False
        self.display = False
        self.refresh(layout=True)

    def highlighted_command(self) -> Command | None:
        option_list = self.query_one("#command-menu-list", OptionList)
        if option_list.highlighted is None:
            return None
        option = option_list.get_option_at_index(option_list.highlighted)
        return _COMMAND_INDEX.get(str(option.id)) if option.id else None

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        command = _COMMAND_INDEX.get(str(event.option.id))
        if command is not None:
            self.post_message(self.Chosen(command))

    def border_color(self) -> str:
        return theme.GARNET
