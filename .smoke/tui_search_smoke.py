"""Headless TUI /search smoke: forced web search -> sources -> ANSWER.

Runs the real Textual app against real Ollama + real DuckDuckGo.
Uses deepseek-r1:8b (the user's default model, which has NO tools capability)
to prove that /search works even for tool-less models.
"""

from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    from textual.widgets import Markdown

    from axiom.core.chat import ChatSession
    from axiom.core.state import GenerationState
    from axiom.frontends.tui.app import AxiomApp, WorkspaceScreen
    from axiom.frontends.tui.widgets.messages import AssistantMessage
    from axiom.frontends.tui.widgets.search import WebSearchPanel

    session = ChatSession()
    session.config.model = "deepseek-r1:8b"
    session.config.think = False
    session.config.search_read_sources = 1  # keep the smoke fast

    app = AxiomApp(session)
    saw_searching = False

    async with app.run_test(size=(110, 34)) as pilot:
        for _ in range(300):
            await pilot.pause(0.05)
            if isinstance(app.screen, WorkspaceScreen):
                break
        else:
            print("FAIL: workspace never opened")
            return 1

        original_send = session.send

        async def watching_send(*args, **kwargs):
            nonlocal saw_searching
            from axiom.core.events import StatusChange

            async for event in original_send(*args, **kwargs):
                if isinstance(event, StatusChange) and event.state is GenerationState.SEARCHING:
                    saw_searching = True
                yield event

        session.send = watching_send  # type: ignore[method-assign]

        screen = app.screen
        assert isinstance(screen, WorkspaceScreen), type(screen).__name__
        screen.handle_submit("/search latest stable Python version")
        for _ in range(6000):
            await pilot.pause(0.1)
            if not screen._generating:
                break
        else:
            print("FAIL: generation never finished (timeout 600s)")
            return 1

        answers = [
            m for m in screen.chat_view.children if isinstance(m, AssistantMessage)
        ]
        if not answers:
            print("FAIL: no AssistantMessage rendered")
            return 1
        assistant = answers[-1]
        panels = list(assistant.query(WebSearchPanel))
        panel = panels[0] if panels else None
        sources = panel.sources if panel is not None else []
        markdown = assistant.query_one("#answer-markdown", Markdown)
        answer = markdown.source.strip()
        state = screen.session.state

        ok = (
            state is GenerationState.COMPLETED
            and saw_searching
            and panel is not None
            and len(sources) > 0
            and len(answer) > 20
        )
        print(
            "TUI-SEARCH:",
            "OK" if ok else "FAIL",
            f"state={state.value} searching_seen={saw_searching} "
            f"panel={'yes' if panel else 'no'} sources={len(sources)} "
            f"answer_chars={len(answer)}",
        )
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
