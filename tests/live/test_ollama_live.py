"""Live checks against a real Ollama server — opt-in, never run by default.

These replace the throwaway probe scripts that used to sit in the repository
root (see ``TODO.md`` §4). Enable them explicitly::

    $env:AXIOM_LIVE_OLLAMA = "1"; python -m pytest tests/live -m ollama

Overridable via environment:

* ``AXIOM_LIVE_MODEL``   — model to exercise (default ``deepseek-r1:8b``)
* ``AXIOM_LIVE_TIMEOUT`` — seconds to wait for real events (default ``300``)
"""

from __future__ import annotations

import asyncio
import os

import pytest

from axiom.core.chat import ChatSession
from axiom.core.config import Config
from axiom.core.events import SearchResultEvent

pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(
        os.environ.get("AXIOM_LIVE_OLLAMA") != "1",
        reason="live Ollama check: set AXIOM_LIVE_OLLAMA=1 to enable",
    ),
]

LIVE_URL = "https://obrmos.ru/kur/kur_obuch/_9_kur_obuch_990.html"
MODEL = os.environ.get("AXIOM_LIVE_MODEL", "deepseek-r1:8b")
TIMEOUT = float(os.environ.get("AXIOM_LIVE_TIMEOUT", "300"))


async def _started_session() -> ChatSession:
    """A session with a real model, or a skip when the server is not usable."""
    session = ChatSession(Config(model=MODEL))
    report = await session.startup()
    if report.selected is None:
        pytest.skip(f"live Ollama unavailable: {report.error or 'no model'}")
    return session


async def test_pasted_link_is_read_from_the_live_web():
    """Regression: a pasted URL must reach the model as real page text.

    ``deepseek-r1`` answers "I cannot fetch live web pages" and emits no tool
    calls of its own, so the agent reads the link itself.
    """
    session = await _started_session()
    seen: list = []

    async def consume() -> None:
        async for event in session.send(f"Что на странице {LIVE_URL} ?"):
            seen.append(event)
            if isinstance(event, SearchResultEvent):
                return

    task = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(task, timeout=TIMEOUT)
    except TimeoutError:  # pragma: no cover - depends on the live server
        pytest.fail(f"no search_result within {TIMEOUT:.0f}s")
    finally:
        session.cancel()
        await asyncio.sleep(0)
        task.cancel()

    results = [event for event in seen if isinstance(event, SearchResultEvent)]
    assert results, "the agent never reported reading the pasted link"
    source = results[0].sources[0]
    assert source.url == LIVE_URL
    assert source.snippet.strip(), "the UI would show an empty source snippet"
