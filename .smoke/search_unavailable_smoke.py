"""Headless smoke: search backend unreachable -> chat survives (TODO §2).

Emulates "no internet" at the application boundary: a provider whose endpoints
point at an unroutable local port with a tiny timeout. A real generation with
``force_search=True`` must surface the failure (failed tool result and/or
``search_unavailable`` error) instead of crashing, and the session must reach
COMPLETED with a non-empty answer.

    $env:AXIOM_HOME = "$PWD\\.smoke\\home-nosearch"; python .smoke\\search_unavailable_smoke.py
"""

from __future__ import annotations

import asyncio
import sys

from axiom.core.chat import ChatSession
from axiom.core.errors import SearchUnavailableError
from axiom.core.search.provider import SearchResult
from axiom.core.state import GenerationState

PROMPT = "Найди в интернете: последняя стабильная версия Python."


class DeadProvider:
    """Search provider whose backend is unreachable (emulates no internet)."""

    name = "Dead"

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        raise SearchUnavailableError(
            "Web search is unavailable.",
            hint="Connection refused (emulated offline).",
        )

    async def fetch(self, url: str, max_chars: int = 4000) -> str:
        raise SearchUnavailableError(
            f"Could not read source: {url}",
            hint="Connection refused (emulated offline).",
        )


async def main() -> int:
    session = ChatSession(provider=DeadProvider())  # type: ignore[arg-type]
    session.config.web_search_enabled = True
    report = await session.startup()
    if not report.ollama_available or not report.models:
        print("FAIL: Ollama is not reachable:", report.error)
        return 1
    model = session.registry.get("deepseek-r1:8b")
    if model is None:
        print("FAIL: deepseek-r1:8b is not installed")
        return 1
    await session.switch_model("deepseek-r1:8b")

    saw_failed_result = False
    answer: list[str] = []
    async for event in session.send(PROMPT, force_search=True):
        if type(event).__name__ == "ToolResultEvent" and not event.ok:
            saw_failed_result = True
            print(f"OK: failed tool result surfaced: {event.error}")
        elif type(event).__name__ == "ErrorEvent":
            print(f"note: error event [{event.kind}]: {event.message}")
        elif type(event).__name__ == "ContentChunk":
            answer.append(event.text)
        elif type(event).__name__ == "StatusChange":
            print("status:", event.state.value, event.detail or "")

    content = "".join(answer).strip()
    state = session.state
    ok = (
        saw_failed_result
        and bool(content)
        and state is GenerationState.COMPLETED
    )
    print(
        "SEARCH-DOWN-SMOKE:",
        "OK" if ok else "FAIL",
        f"state={state.value} failed_result={saw_failed_result} answer={content[:120]!r}",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
