"""Headless splash-failure smoke: dead Ollama -> failure UI -> Retry re-probes.

Point AXIOM at a dead port. The splash must show the real failure with Retry
and Exit actions; Retry must actually re-run the startup probes (and fail
again while the endpoint stays dead).
"""

from __future__ import annotations

import asyncio
import os
import sys

from textual.css.query import NoMatches

DEAD_URL = "http://127.0.0.1:9"


async def main() -> int:
    from axiom.frontends.tui.app import AxiomApp
    from axiom.frontends.tui.widgets.splash import ActionOption, SplashScreen

    session = ChatSessionStub()
    app = AxiomApp(session)

    async with app.run_test(size=(110, 34)) as pilot:
        screen = app.screen
        assert isinstance(screen, SplashScreen), type(screen).__name__
        for _ in range(200):
            await pilot.pause(0.1)
            if screen._finished:
                break
        else:
            print("FAIL: splash never finished probing")
            return 1
        # _finished flips before the failure UI is mounted; wait for it.
        for _ in range(50):
            try:
                screen.query_one("#splash-message")
                break
            except NoMatches:
                await pilot.pause(0.1)
        else:
            print("FAIL: failure UI never mounted")
            print("screen type:", type(screen).__name__, "id:", screen.id)
            print("children:", [f"{type(c).__name__}:{c.id}" for c in screen.children])
            print(
                "screens:",
                [f"{type(s).__name__}:{s.id}" for s in app.screen_stack],
            )
            print("app.screen is screen:", app.screen is screen)
            return 1

        actions = list(screen.query(ActionOption))
        ok = (
            screen._failed_reason is not None
            and len(actions) == 2
            and {a.label_text for a in actions} == {"Retry", "Exit"}
        )
        print(
            "SPLASH-FAIL:",
            "OK" if ok else "FAIL",
            f"reason={screen._failed_reason!r} actions={[a.label_text for a in actions]}",
        )
        if not ok:
            return 1

        # Retry must genuinely re-run the probes.
        screen._retry()
        for _ in range(200):
            await pilot.pause(0.1)
            if screen._finished:
                break
        else:
            print("FAIL: Retry never re-ran the probes")
            return 1
        retry_ok = (
            isinstance(app.screen, SplashScreen)
            and screen._failed_reason is not None
            and app.screen is screen
        )
        print(
            "SPLASH-RETRY:",
            "OK" if retry_ok else "FAIL",
            f"reason={screen._failed_reason!r}",
        )
        if not retry_ok:
            return 1

        # Exit must really terminate the app.
        screen._activate("Exit")
        for _ in range(50):
            await pilot.pause(0.1)
            if app.return_code is not None:
                break
        else:
            print("FAIL: Exit did not terminate the app")
            return 1
        print("SPLASH-EXIT: OK return_code =", app.return_code)
        return 0


def ChatSessionStub():  # noqa: N802 - mirrors ChatSession, dead endpoint
    from pathlib import Path

    from axiom.core.chat import ChatSession
    from axiom.core.config import Config

    # The Ollama client is built from the persisted config at construction,
    # so the dead endpoint must be on disk BEFORE ChatSession() runs.
    home = Path(os.environ["AXIOM_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    config = Config()
    config.ollama_url = DEAD_URL
    config.save()
    return ChatSession()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
