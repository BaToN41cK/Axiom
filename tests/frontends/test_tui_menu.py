"""TUI regression tests for the slash-command autocomplete menu."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from textual.app import App, ComposeResult
from textual.pilot import Pilot

from axiom.core.chat import ChatSession
from axiom.frontends.tui.app import WorkspaceScreen
from axiom.frontends.tui.widgets.commands import CommandMenu
from axiom.frontends.tui.widgets.prompt import InputBar


class _TuiHarness(App):
    """Minimal app mounting the real WorkspaceScreen (no splash, no Ollama)."""

    CSS_PATH = "../../src/axiom/frontends/tui/theme.tcss"

    def __init__(self) -> None:
        super().__init__()
        self.session = ChatSession()

    def compose(self) -> ComposeResult:
        yield WorkspaceScreen(self.session)


@asynccontextmanager
async def workspace() -> AsyncIterator[tuple[App, Pilot]]:
    """Run the real WorkspaceScreen; kept inside the test's own context."""
    app = _TuiHarness()
    async with app.run_test(size=(100, 30)) as pilot:
        for _ in range(2):
            await pilot.pause()
        yield app, pilot


async def test_startup_focus_is_prompt() -> None:
    """The prompt holds focus at startup (auto-focus must not steal it)."""
    async with workspace() as (app, _pilot):
        bar = app.screen.query_one(InputBar)
        assert app.focused is bar.input


async def test_slash_opens_menu() -> None:
    async with workspace() as (app, pilot):
        bar = app.screen.query_one(InputBar)
        menu = bar.query_one(CommandMenu)

        await pilot.press("/")
        await pilot.pause()
        await pilot.pause()

        assert bar.input.text == "/"
        assert menu.open is True
        assert menu.display is True
        assert menu.highlighted_command() is not None


async def test_menu_filters_and_navigates() -> None:
    async with workspace() as (app, pilot):
        bar = app.screen.query_one(InputBar)
        menu = bar.query_one(CommandMenu)

        await pilot.press("/", "h", "e")
        await pilot.pause()
        await pilot.pause()

        assert bar.input.text == "/he"
        assert menu.open is True

        highlighted = menu.highlighted_command()
        assert highlighted is not None
        assert highlighted.name == "/help"

        # At least two candidates match "/he"; arrow-down moves the highlight.
        await pilot.press("down")
        await pilot.pause()
        second = menu.highlighted_command()
        assert second is not None


async def test_enter_completes_partial_token() -> None:
    """Enter on a partial token completes it; the menu stays for further edits."""
    async with workspace() as (app, pilot):
        bar = app.screen.query_one(InputBar)
        menu = bar.query_one(CommandMenu)

        await pilot.press("/", "h", "e")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert bar.input.text == "/help"
        # show_for re-opens the menu for the completed token; the next Enter
        # executes it (exact match) — see test_enter_executes_exact_command.
        assert menu.open is True


async def test_enter_executes_exact_command() -> None:
    """Enter on an exact token executes it, clears the prompt, closes the menu."""
    async with workspace() as (app, pilot):
        bar = app.screen.query_one(InputBar)
        menu = bar.query_one(CommandMenu)

        await pilot.press("/", "h", "e", "l", "p")
        await pilot.pause()
        assert menu.open is True

        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert bar.input.text == ""
        assert menu.open is False


async def test_typing_argument_hides_menu() -> None:
    """A trailing space means the command is settled: the menu closes."""
    async with workspace() as (app, pilot):
        bar = app.screen.query_one(InputBar)
        menu = bar.query_one(CommandMenu)

        await pilot.press("/", "m", "o")
        await pilot.pause()
        assert menu.open is True

        await pilot.press("space")
        await pilot.pause()
        await pilot.pause()
        assert bar.input.text == "/mo "
        assert menu.open is False


async def test_plain_text_never_opens_menu() -> None:
    async with workspace() as (app, pilot):
        bar = app.screen.query_one(InputBar)
        menu = bar.query_one(CommandMenu)

        await pilot.press("h", "i")
        await pilot.pause()
        await pilot.pause()

        assert bar.input.text == "hi"
        assert menu.open is False
        assert menu.display is False