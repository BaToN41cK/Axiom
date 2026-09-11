"""AXIOM live task log — visual journal of agent work."""

import time
from dataclasses import dataclass, field

from rich.text import Text

from src.ui.theme import SYMBOLS

# Step name column width and right edge for detail values.
# Responsive: capped so the layout survives narrow terminals.
_NAME_WIDTH = 32
_DETAIL_WIDTH = 12


@dataclass
class Step:
    """A single step in the agent workflow."""

    name: str
    state: str = "pending"  # pending | active | done | failed
    detail: str = ""
    note: str = ""  # sub-line shown while the step is active
    started_at: float = 0.0


class TaskLog:
    """Ordered log of agent workflow steps.

    Steps are rendered live (◐ active → ✓ done) and, once the task
    completes, the final render becomes part of the scrollback history.
    """

    def __init__(self):
        self.steps: list[Step] = []

    def _find(self, name: str):
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def start(self, name: str, note: str = ""):
        """Start (or restart) a step, with an optional activity note."""
        step = self._find(name)
        if step is None:
            step = Step(name=name)
            self.steps.append(step)
        step.state = "active"
        step.note = note
        step.started_at = time.time()

    def complete(self, name: str, detail: str = ""):
        """Complete a step. Without an explicit detail, the duration is used."""
        step = self._find(name)
        if step is None:
            return
        step.state = "done"
        if not detail and step.started_at > 0:
            detail = f"{time.time() - step.started_at:.1f}s"
        step.started_at = 0
        step.detail = detail

    def fail(self, name: str, detail: str = "failed"):
        """Mark a step as failed."""
        step = self._find(name)
        if step is None:
            return
        step.state = "failed"
        step.started_at = 0
        step.detail = detail

    def cancel_active(self, detail: str = "cancelled"):
        """Complete all active steps as cancelled."""
        for step in self.steps:
            if step.state == "active":
                step.state = "done"
                step.detail = detail
                step.started_at = 0

    def render(self) -> Text:
        """Render all steps as plain inline journal lines (no boxes)."""
        text = Text()
        for step in self.steps:
            if step.state == "done":
                text.append(f"  {SYMBOLS['success']} {step.name:<{_NAME_WIDTH}}",
                            style="status.success")
                if step.detail:
                    text.append(f"{step.detail:>{_DETAIL_WIDTH}}", style="status")
                text.append("\n")
            elif step.state == "active":
                text.append(f"  {SYMBOLS['active']} {step.name}...\n",
                            style="status.active")
                if step.note:
                    text.append(f"    {step.note}\n", style="muted")
            elif step.state == "failed":
                text.append(f"  {SYMBOLS['error']} {step.name:<{_NAME_WIDTH}}",
                            style="status.error")
                if step.detail:
                    text.append(f"{step.detail:>{_DETAIL_WIDTH}}", style="status.error")
                text.append("\n")
        return text
