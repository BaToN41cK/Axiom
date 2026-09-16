"""Headless smoke: tool-call initiated by the model itself (TODO §2).

Runs a real ChatSession against the real Ollama (gemma4:12b, capability
``tools``) with ``web_search_enabled = True`` and a prompt that cannot be
answered without fresh data. The model must call ``web_search`` on its own
(no ``force_search``), receive results and produce a final answer.

Pass criteria: ToolCallEvent(web_search) → ToolResultEvent(ok) → non-empty
final answer → state COMPLETED.

    $env:AXIOM_HOME = "$PWD\\.smoke\\home-modeltool"; python .smoke\\model_tool_smoke.py
"""

from __future__ import annotations

import asyncio
import sys

from axiom.core.chat import ChatSession
from axiom.core.events import (
    ContentChunk,
    ErrorEvent,
    StatusChange,
    ToolCallEvent,
    ToolResultEvent,
)
from axiom.core.state import GenerationState

PROMPT = (
    "Найди в интернете актуальную стабильную версию Python и назови её в ответе. "
    "Используй поиск."
)


async def main() -> int:
    session = ChatSession()
    session.config.web_search_enabled = True
    report = await session.startup()
    if not report.ollama_available or not report.models:
        print("FAIL: Ollama is not reachable:", report.error)
        return 1

    model = session.registry.get("gemma4:12b")
    if model is None or not model.supports("tools"):
        print("FAIL: gemma4:12b with capability 'tools' is not installed")
        return 1
    await session.switch_model("gemma4:12b")

    saw_call = saw_ok_result = False
    answer: list[str] = []
    async for event in session.send(PROMPT):
        if isinstance(event, ToolCallEvent):
            if event.name == "web_search":
                saw_call = True
                print(f"OK: model-initiated tool_call web_search {event.arguments}")
        elif isinstance(event, ToolResultEvent):
            if event.ok:
                saw_ok_result = True
                print(f"OK: tool_result ok ({event.duration_ms} ms)")
            else:
                print(f"note: tool_result failed: {event.error}")
        elif isinstance(event, ContentChunk):
            answer.append(event.text)
        elif isinstance(event, StatusChange):
            print("status:", event.state.value, event.detail or "")
        elif isinstance(event, ErrorEvent):
            print("error:", event.message)

    content = "".join(answer).strip()
    state = session.state
    ok = saw_call and saw_ok_result and bool(content) and state is GenerationState.COMPLETED
    print(
        "MODEL-TOOL-SMOKE:",
        "OK" if ok else "FAIL",
        f"state={state.value} tool_call={saw_call} result_ok={saw_ok_result} "
        f"answer={content[:120]!r}",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
