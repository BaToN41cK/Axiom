"""Headless TUI smoke check: splash -> workspace -> real generation -> ANSWER.

Runs the real Textual app (AxiomApp.run_test) against the real Ollama server.
Exits 0 only if the workspace opened, the answer was actually rendered and the
final state is COMPLETED.
"""

from __future__ import annotations

import asyncio
import os
import sys

MODEL = os.environ.get("AXIOM_SMOKE_MODEL", "gemma4:12b")
PROMPT = os.environ.get("AXIOM_SMOKE_PROMPT", "Reply with exactly: PONG")


async def main() -> int:
    from textual.widgets import Markdown

    from axiom.core.chat import ChatSession
    from axiom.core.state import GenerationState
    from axiom.frontends.tui.app import AxiomApp, WorkspaceScreen
    from axiom.frontends.tui.widgets.messages import AssistantMessage

    session = ChatSession()
    session.config.model = MODEL
    session.config.think = False
    session.config.web_search_enabled = False

    app = AxiomApp(session)
    async with app.run_test(size=(110, 34)) as pilot:
        for _ in range(300):
            await pilot.pause(0.05)
            if isinstance(app.screen, WorkspaceScreen):
                break
        else:
            print(
                "FAIL: workspace never opened; screen =",
                type(app.screen).__name__,
            )
            return 1

        screen = app.screen
        assert isinstance(screen, WorkspaceScreen), type(screen).__name__
        print("OK: workspace opened after splash")
        screen.handle_submit(PROMPT)
        for _ in range(1500):
            await pilot.pause(0.1)
            if not screen._generating:
                break
        else:
            print("FAIL: generation never finished (timeout 150s)")
            return 1

        answers = [
            m for m in screen.chat_view.children if isinstance(m, AssistantMessage)
        ]
        if not answers:
            print("FAIL: no AssistantMessage rendered")
            return 1
        assistant = answers[-1]
        markdown = assistant.query_one("#answer-markdown", Markdown)
        state = screen.session.state
        visible = bool(markdown.source.strip())
        ok = state is GenerationState.COMPLETED and visible and "PONG" in markdown.source
        print(
            "TUI-SMOKE:",
            "OK" if ok else "FAIL",
            f"state={state.value} answer={markdown.source.strip()!r} finished={assistant.finished}",
        )
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
