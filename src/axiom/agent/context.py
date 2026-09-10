"""Context manager: token budget, truncation, compaction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from axiom.core.logging import get_logger

logger = get_logger("context")

# Rough estimate: ~4 chars per token (works well enough for budgeting).
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count for text."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class ContextStats:
    used: int = 0
    budget: int = 100_000
    compacted_count: int = 0

    @property
    def percent(self) -> float:
        return 100.0 * self.used / max(1, self.budget)

    @property
    def needs_compaction(self) -> bool:
        return self.percent >= 80.0


class ContextManager:
    """Manages the conversation context within a token budget.

    Prioritization: system prompt and task are kept; old tool outputs are
    dropped first, then oldest conversation turns are summarized away.
    """

    def __init__(self, budget: int = 100_000, keep_recent: int = 8) -> None:
        self.budget = budget
        self.keep_recent = keep_recent
        self.messages: list[dict[str, Any]] = []
        self.compactions = 0
        self._task = ""

    @property
    def compacted_count(self) -> int:
        """Number of compactions performed."""
        return self.compactions

    def set_task(self, task: str) -> None:
        self._task = task

    def stats(self) -> ContextStats:
        used = sum(estimate_tokens(str(m.get("content", ""))) for m in self.messages)
        used += sum(
            estimate_tokens(str(tc))
            for m in self.messages
            for tc in m.get("tool_calls", [])
        )
        return ContextStats(used=used, budget=self.budget, compacted_count=self.compactions)

    # -- messages ----------------------------------------------------------
    def add(self, message: dict[str, Any]) -> None:
        self.messages.append(dict(message))

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        # Truncate giant tool outputs immediately.
        max_chars = 8000
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... [truncated {len(content) - max_chars} chars]"
        self.messages.append(
            {"role": "tool", "tool_call_id": tool_call_id, "name": name, "content": content}
        )

    # -- compaction ----------------------------------------------------------
    def maybe_compact(self, summarizer: Any = None) -> bool:
        """Compact context when nearing the budget.

        summarizer: optional async callable(list[str]) -> str used to summarize
        dropped turns. Without it, turns are dropped with a marker.
        """
        if not self.stats().needs_compaction:
            return False
        self.compact(summarizer)
        return True

    def compact(self, summarizer: Any = None) -> None:
        self.compactions += 1
        protected: list[dict[str, Any]] = []
        droppable: list[int] = []
        for i, message in enumerate(self.messages):
            role = message.get("role")
            if role == "system":
                protected.append(message)
            elif role == "tool":
                # drop all but the last few tool outputs
                droppable.append(i)
            elif role == "user" and i == self._first_user_index():
                protected.append(message)
        # keep recent tail
        tail_start = max(0, len(self.messages) - self.keep_recent)
        for i in droppable:
            if i >= tail_start:
                protected.append(self.messages[i])
        dropped_text = [
            str(self.messages[i].get("content", ""))[:500]
            for i in droppable
            if i < tail_start
        ]
        new_messages: list[dict[str, Any]] = list(protected)
        summary_marker = (
            f"[context compacted {self.compactions}x; {len(dropped_text)} older "
            "tool outputs/turns removed]"
        )
        new_messages.insert(
            1 if new_messages and new_messages[0].get("role") == "system" else 0,
            {"role": "assistant", "content": summary_marker},
        )
        self.messages = new_messages
        logger.info("Context compacted #%d", self.compactions)

    def _first_user_index(self) -> int:
        for i, message in enumerate(self.messages):
            if message.get("role") == "user":
                return i
        return -1

    def render_task_block(self, project_summary: str = "") -> str:
        """Build the system block sent to the model."""
        parts = ["You are Axiom, a terminal-first AI coding agent."]
        if project_summary:
            parts.append(f"Project context:\n{project_summary}")
        if self._task:
            parts.append(f"Current task: {self._task}")
        return "\n\n".join(parts)
