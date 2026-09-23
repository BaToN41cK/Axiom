"""Headless performance benchmark runner with cold/warm runs and JSON export."""
from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from axiom.core.performance import PerformanceMetrics, summarize_runs


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    prompt: str
    system_prompt: str | None = None
    cold: bool = True


@dataclass
class BenchmarkResult:
    scenario: str
    phase: str
    repetition: int
    ok: bool
    duration_ms: float
    error: str | None = None
    metrics: dict = field(default_factory=dict)


class BenchmarkRunner:
    def __init__(self, session_factory: Callable[[], Awaitable[object]],
                 scenarios: list[BenchmarkScenario], *, repetitions: int = 3,
                 output: str | Path | None = None) -> None:
        if repetitions < 1:
            raise ValueError("repetitions must be >= 1")
        self.session_factory = session_factory
        self.scenarios = scenarios
        self.repetitions = repetitions
        self.output = Path(output) if output else None

    async def run(self) -> dict:
        results: list[BenchmarkResult] = []
        profiles: list[PerformanceMetrics] = []
        for scenario in self.scenarios:
            candidate = self.session_factory()
            session = await candidate if hasattr(candidate, "__await__") else candidate
            try:
                startup = getattr(session, "startup", None)
                if startup is not None:
                    await startup()
            except Exception:
                pass
            for index in range(self.repetitions):
                phase = "cold" if index == 0 and scenario.cold else "warm"
                started = time.perf_counter()
                try:
                    [event async for event in session.send(scenario.prompt)]
                    perf = getattr(getattr(session, "agent", None), "perf", None)
                    if perf is None:
                        raise RuntimeError("agent did not produce PerformanceMetrics")
                    metric = perf.model_copy(update={"scenario": scenario.name, "run_index": index})
                    metric.cold = phase == "cold"
                    metric.finalize()
                    profiles.append(metric)
                    result = BenchmarkResult(
                        scenario.name, phase, index, True,
                        round((time.perf_counter() - started) * 1000, 2),
                        metrics=metric.model_dump(),
                    )
                except Exception as exc:
                    result = BenchmarkResult(scenario.name, phase, index, False,
                                             round((time.perf_counter() - started) * 1000, 2),
                                             error=f"{type(exc).__name__}: {exc}")
                results.append(result)
        report = {"schema_version": 1, "generated_at": time.time(), "repetitions": self.repetitions,
                  "scenarios": [s.name for s in self.scenarios], "runs": [r.__dict__ for r in results],
                  "summary": summarize_runs(profiles) if profiles else {}}
        if self.output is not None:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report


def scenarios_from_json(path: str | Path) -> list[BenchmarkScenario]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("scenarios", raw) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("benchmark file must contain a scenario list")
    return [BenchmarkScenario(str(i["name"]), str(i["prompt"]), i.get("system_prompt"), bool(i.get("cold", True)))
            for i in items if isinstance(i, dict) and i.get("name") and i.get("prompt")]
