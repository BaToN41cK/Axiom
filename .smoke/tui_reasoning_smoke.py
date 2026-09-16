"""Headless TUI reasoning smoke (deepseek-r1:8b): THINKING -> ANSWER -> COMPLETED.

Verifies the flagship UX contract end-to-end in the real Textual app:
  - real reasoning deltas stream into a ReasoningPanel (live view);
  - after THINKING -> ANSWERING the panel is collapsed and the reasoning text
    never leaks into the final answer markdown;
  - the answer itself is rendered and the state ends COMPLETED.
"""

from __future__ import annotations

import asyncio
import sys

PROMPT = "Reply with exactly: OK"


async def main() -> int:
    from textual.widgets import Collapsible, Markdown

    from axiom.core.chat import ChatSession
    from axiom.core.events import ReasoningChunk
    from axiom.core.state import GenerationState
    from axiom.frontends.tui.app import AxiomApp, WorkspaceScreen
    from axiom.frontends.tui.widgets.messages import AssistantMessage

    session = ChatSession()
    session.config.model = "deepseek-r1:8b"
    session.config.think = True
    session.config.web_search_enabled = False
    session.config.reasoning_expanded = True  # reproduce the live-view scenario

    app = AxiomApp(session)
    reasoning_chars = 0

    async with app.run_test(size=(110, 34)) as pilot:
        for _ in range(300):
            await pilot.pause(0.05)
            if isinstance(app.screen, WorkspaceScreen):
                break
        else:
            print("FAIL: workspace never opened")
            return 1

        original_send = session.send

        async def counting_send(*args, **kwargs):
            nonlocal reasoning_chars
            async for event in original_send(*args, **kwargs):
                if isinstance(event, ReasoningChunk):
                    reasoning_chars += len(event.text)
                yield event

        session.send = counting_send  # type: ignore[method-assign]

        screen = app.screen
        assert isinstance(screen, WorkspaceScreen), type(screen).__name__
        screen.handle_submit(PROMPT)
        for _ in range(1800):
            await pilot.pause(0.1)
            if not screen._generating:
                break
        else:
            print("FAIL: generation never finished (timeout 180s)")
            return 1

        answers = [
            m for m in screen.chat_view.children if isinstance(m, AssistantMessage)
        ]
        if not answers:
            print("FAIL: no AssistantMessage rendered")
            return 1
        assistant = answers[-1]
        markdown = assistant.query_one("#answer-markdown", Markdown)
        answer_text = markdown.source.strip()
        state = screen.session.state
        panel = assistant.reasoning_panel
        panel_collapsed = (
            panel.query_one("#reasoning-collapsible", Collapsible).collapsed
            if panel is not None
            else None
        )

        ok = (
            state is GenerationState.COMPLETED
            and reasoning_chars > 0
            and answer_text == "OK"
            and assistant.finished
            and panel is not None
            and panel_collapsed  # the live reasoning view must fold itself away
        )
        print(
            "TUI-REASONING:",
            "OK" if ok else "FAIL",
            f"state={state.value} reasoning_chars={reasoning_chars} "
            f"answer={answer_text!r} panel={'yes' if panel else 'no'} "
            f"panel_collapsed={panel_collapsed}",
        )
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
