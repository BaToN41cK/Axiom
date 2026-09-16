"""Performance benchmark (§34 of the original specification).

Measures real latency metrics against the live Ollama server:

- ``TTFT``            — time to first event of any kind
- ``first_reasoning`` — time to the first reasoning chunk (reasoning models)
- ``first_content``   — time to the first content chunk
- ``total``           — wall time until the ``Done`` event
- ``tok/s``           — real throughput reported by Ollama (Done.tokens_per_second)

Usage:

    $env:AXIOM_HOME = "$PWD\\.smoke\\home-bench"; python .smoke\\benchmark.py

Exits 0 when every run completes; prints a §34-style table.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from axiom.core.chat import ChatSession
from axiom.core.events import ContentChunk, Done, ReasoningChunk
from axiom.core.state import GenerationState

PROMPT = os.environ.get("AXIOM_BENCH_PROMPT", "Кратко (2-3 предложения): зачем нужно покрытие кода тестами?")
RUNS_PER_MODEL = int(os.environ.get("AXIOM_BENCH_RUNS", "2"))

# (model, think flag, column label) — mirrors §34: a reasoning model and a
# content-only model.
SUITES: list[tuple[str, bool | None, str]] = [
    ("deepseek-r1:8b", None, "reasoning"),
    ("gemma4:12b", False, "content-only"),
]


async def run_once(session, model: str, think: bool | None) -> dict | None:
    """One measured generation; returns the metrics dict or None on failure."""
    session.config.model = model
    session.config.think = think
    session.config.web_search_enabled = False

    t0 = time.perf_counter()
    first_event: float | None = None
    first_reasoning: float | None = None
    first_content: float | None = None
    done = None

    async for event in session.send(PROMPT):
        now = time.perf_counter() - t0
        if first_event is None:
            first_event = now
        if isinstance(event, ReasoningChunk) and first_reasoning is None:
            first_reasoning = now
        elif isinstance(event, ContentChunk) and first_content is None:
            first_content = now
        elif isinstance(event, Done):
            done = event
    total = time.perf_counter() - t0

    if done is None:
        return None
    return {
        "ttft": first_event,
        "first_reasoning": first_reasoning,
        "first_content": first_content,
        "total": total,
        "tok_s": done.tokens_per_second,
        "tokens_out": done.tokens_out,
        "duration_ms": done.duration_ms,
    }


async def main() -> int:
    session = ChatSession()
    report = await session.startup()
    if not report.ollama_available or not report.models:
        print("FAIL: Ollama is not reachable:", report.error)
        return 1

    rows: list[tuple[str, str, dict]] = []
    for model, think, label in SUITES:
        resolved = session.registry.get(model) or next(
            (m for m in report.models if model in m.name), None
        )
        if resolved is None:
            print(f"SKIP: model {model} is not installed")
            continue
        for run in range(1, RUNS_PER_MODEL + 1):
            print(f"running {model} (run {run}/{RUNS_PER_MODEL}) ...", flush=True)
            metrics = await run_once(session, model, think)
            if metrics is None:
                print(f"FAIL: no Done event for {model}")
                return 1
            if session.state is not GenerationState.COMPLETED:
                print(f"FAIL: {model} finished in state {session.state.value}")
                return 1
            rows.append((model, label, metrics))

    print()
    header = f"{'model':<18}{'mode':<14}{'TTFT':>8}{'rsn':>8}{'cnt':>8}{'total':>8}{'tok/s':>9}{'out':>7}"
    print(header)
    print("-" * len(header))
    for model, label, m in rows:
        rsn = f"{m['first_reasoning']:.2f}s" if m["first_reasoning"] is not None else "—"
        cnt = f"{m['first_content']:.2f}s" if m["first_content"] is not None else "—"
        rate = f"{m['tok_s']:.1f}" if m["tok_s"] is not None else "—"
        print(
            f"{model:<18}{label:<14}"
            f"{m['ttft']:>7.2f}s{rsn:>8}{cnt:>8}{m['total']:>7.2f}s{rate:>9}{m['tokens_out'] or 0:>7}"
        )
    print("\nBENCH: OK" if rows else "BENCH: no runs")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
