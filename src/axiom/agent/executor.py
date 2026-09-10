"""Executor: automatic verification pipeline (format -> lint -> test -> build)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from axiom.core.logging import get_logger
from axiom.tools.terminal import run_shell

logger = get_logger("executor")


@dataclass
class VerificationStep:
    name: str
    command: str
    ran: bool = False
    passed: bool = False
    output: str = ""


class Verifier:
    """Runs a verification pipeline after changes; bounded repair support."""

    def __init__(self, workspace: str, max_repair_cycles: int = 3) -> None:
        self.workspace = workspace
        self.max_repair_cycles = max_repair_cycles

    async def verify(self, pipeline: list[tuple[str, str]]) -> dict[str, Any]:
        """Run (name, command) steps; stop at first failing step."""
        results: list[VerificationStep] = []
        for name, command in pipeline:
            code, out, err = await run_shell(command, self.workspace, timeout=300.0)
            step = VerificationStep(
                name=name, command=command, ran=True,
                passed=code == 0, output=(out + err)[-3000:],
            )
            results.append(step)
            if code != 0:
                break
        passed = all(s.passed for s in results) and bool(results)
        return {"passed": passed, "steps": [s.__dict__ for s in results]}

    def default_pipeline(self, project) -> list[tuple[str, str]]:
        """Build a pipeline from detected project properties."""
        pipeline: list[tuple[str, str]] = []
        if project.language == "Python":
            pipeline.append(("test", "python -m pytest -q --no-header"))
        elif project.test_framework:
            pipeline.append(("test", project.test_framework))
        return pipeline
