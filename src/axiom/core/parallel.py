"""Parallel execution саб­агентов (п.8/28): asyncio.gather + merge + review."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

Runner = Callable[..., Awaitable[dict]]


@dataclass
class ParallelResult:
    results: list[dict] = field(default_factory=list)
    merged: dict = field(default_factory=dict)
    duration_ms: int = 0


async def run_parallel(tasks: list[dict], runner: Runner,
                       *, limit: int = 4, trajectory=None) -> ParallelResult:
    started = time.perf_counter()
    semaphore = asyncio.Semaphore(max(1, limit))

    async def _one(task: dict) -> dict:
        async with semaphore:
            if trajectory is not None:
                try:
                    trajectory.append("agent.start", f"{task.get('agent')}: {str(task.get('task'))[:120]}",
                                      actor=str(task.get("agent") or ""))
                except Exception:
                    pass
            try:
                out = await runner(**task)
                result = {"status": "done", **dict(out or {})}
            except Exception as exc:
                result = {"status": "failed", "agent": task.get("agent"),
                          "error": f"{type(exc).__name__}: {exc}"}
            if trajectory is not None:
                try:
                    trajectory.append(f"agent.{result['status']}", str(task.get("agent")),
                                      actor=str(task.get("agent") or ""), data=result)
                except Exception:
                    pass
            return result

    results = await asyncio.gather(*[_one(t) for t in tasks])
    merged: dict = {"ok": all(r.get("status") == "done" for r in results),
                    "count": len(results),
                    "agents": [r.get("agent") for r in results]}
    duration_ms = int((time.perf_counter() - started) * 1000)
    if trajectory is not None:
        try:
            trajectory.append("orchestrator.merge", f"merged {len(results)} subagents",
                              actor="orchestrator",
                              data={"duration_ms": duration_ms, **merged})
        except Exception:
            pass
    return ParallelResult(results=list(results), merged=merged, duration_ms=duration_ms)
