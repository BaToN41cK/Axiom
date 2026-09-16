"""Headless TUI cancellation smoke: stop mid-thinking -> CANCELLED, no Completed.

Starts a real generation (deepseek-r1:8b thinks slowly), cancels it through the
real binding path (Escape -> action_stop_generation -> session.cancel) and
verifies the state machine lands in CANCELLED with the stream actually stopped.
"""

from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    from axiom.core.state import GenerationState
    from axiom.frontends.tui.app import AxiomApp, WorkspaceScreen
    from axiom.frontends.tui.widgets.messages import AssistantMessage

    session = ChatSessionStub()
    app = AxiomApp(session)

    async with app.run_test(size=(110, 34)) as pilot:
        for _ in range(300):
            await pilot.pause(0.05)
            if isinstance(app.screen, WorkspaceScreen):
                break
        else:
            print("FAIL: workspace never opened")
            return 1

        screen = app.screen
        assert isinstance(screen, WorkspaceScreen), type(screen).__name__
        screen.handle_submit("Reply with exactly: OK")
        # Wait until the model is really producing (busy) before cancelling.
        for _ in range(300):
            await pilot.pause(0.1)
            if screen.session.state.is_busy:
                break
        else:
            print("FAIL: generation never became busy")
            return 1
        # Give the stream a moment so we cancel mid-flight, not at t=0.
        await pilot.pause(3.0)

        screen._request_stop()
        for _ in range(200):
            await pilot.pause(0.1)
            if not screen._generating:
                break
        else:
            print("FAIL: generation never stopped after cancel")
            return 1

        state = screen.session.state
        answers = [
            m for m in screen.chat_view.children if isinstance(m, AssistantMessage)
        ]
        assistant_state = answers[-1]._state if answers else None
        ok = state is GenerationState.CANCELLED and assistant_state is GenerationState.CANCELLED
        print(
            "TUI-CANCEL:",
            "OK" if ok else "FAIL",
            f"session_state={state.value} assistant_state={assistant_state.value if assistant_state else None}",
        )
        return 0 if ok else 1


def ChatSessionStub():  # noqa: N802 - real session against the local Ollama
    from axiom.core.chat import ChatSession

    session = ChatSession()
    session.config.model = "deepseek-r1:8b"
    session.config.think = True
    session.config.web_search_enabled = False
    return session


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
