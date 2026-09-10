"""Planner: produces a task plan (model-assisted with heuristic fallback)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanStep:
    index: int
    description: str
    tool_hint: str = ""
    status: str = "pending"


@dataclass
class Plan:
    task: str
    steps: list[PlanStep] = field(default_factory=list)

    def render(self) -> str:
        lines = ["PLAN"]
        marks = {"pending": "○", "done": "✓", "active": "●"}
        for step in self.steps:
            lines.append(f"{marks.get(step.status, '○')} {step.description}")
        return "\n".join(lines)


HEURISTIC_PLAN: dict[str, list[str]] = {
    "default": [
        "Inspect project structure",
        "Locate relevant code",
        "Prepare changes",
        "Apply changes",
        "Run tests",
        "Verify and report",
    ],
}


class Planner:
    """Builds a plan for a task.

    The plan itself is heuristic scaffolding for the UI; the model still
    decides every concrete action in the loop.
    """

    def create_plan(self, task: str) -> Plan:
        lowered = task.lower()
        steps = list(HEURISTIC_PLAN["default"])
        if "test" in lowered or "тест" in lowered:
            steps = ["Discover test framework", "Run tests", "Analyze failures",
                     "Fix issues", "Re-run tests", "Report"]
        elif "review" in lowered or "ревью" in lowered:
            steps = ["Inspect diff and changed files", "Analyze bugs/security/performance",
                     "Compile findings", "Report with severities"]
        return Plan(task=task, steps=[PlanStep(index=i, description=s)
                                      for i, s in enumerate(steps)])
