"""Context Window Manager — monitors conversation size and summarises when needed.

The agent loop pushes messages through this module which:
1. Tracks the total token estimate (conservative char-based heuristic).
2. When the estimate exceeds a configurable threshold, it summarises older
   messages, keeping the system prompt and the most recent exchanges intact.
3. Falls back gracefully when summarisation itself fails.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from axiom.core.events import Message
from axiom.core.logging import get_logger

_LOG = get_logger("context")

#: Very rough heuristic: 1 token ≈ 4 characters for most models.
_CHARS_PER_TOKEN = 4.0

#: Default max context tokens if the model doesn't report a limit.
_DEFAULT_MAX_TOKENS = 8192

#: Fraction of the context window at which compaction triggers.
_COMPACT_RATIO = 0.75


@dataclass
class ContextReport:
    """Result of a context check."""

    total_chars: int = 0
    estimated_tokens: int = 0
    max_tokens: int = _DEFAULT_MAX_TOKENS
    compacted: bool = False
    summarised_count: int = 0
    kept_count: int = 0
    summary: str | None = None
class ContextManager:
    """Owns the compaction logic.

    Usage in the agent loop::

        ctx = ContextManager(max_tokens=model.context_length or 8192)
        messages = ctx.prepare(history, system_prompt)
        ...
        if ctx.should_compact:
            summary = await ctx.summarise(history, ...)
            history = ctx.compact(history, summary)
    """

    def __init__(self, max_tokens: int | None = None) -> None:
        self._max_tokens = max_tokens or _DEFAULT_MAX_TOKENS
        self._token_limit = int(self._max_tokens * _COMPACT_RATIO)
        self._report = ContextReport()

    # ------------------------------------------------------------------ public

    @property
    def report(self) -> ContextReport:
        return self._report

    @property
    def should_compact(self) -> bool:
        """Whether the conversation exceeds the compaction threshold."""
        return self._report.estimated_tokens > self._token_limit

    def estimate(self, messages: Sequence[dict[str, Any] | Message]) -> int:
        """Rough token estimate from character count."""
        chars = 0
        for msg in messages:
            if isinstance(msg, dict):
                chars += len(msg.get("content", "") or "")
                chars += len(msg.get("thinking", "") or "")
            else:
                chars += len(msg.content or "")
                chars += len(msg.thinking or "")
        return int(chars / _CHARS_PER_TOKEN)

    def prepare(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build the message list to send, respecting context limits."""
        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        estimated = int(total_chars / _CHARS_PER_TOKEN)

        self._report = ContextReport(
            total_chars=total_chars,
            estimated_tokens=estimated,
            max_tokens=self._max_tokens,
        )

        result: list[dict[str, Any]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})

        working = list(messages)
        while self.estimate(result + working) > self._token_limit and len(working) > 1:
            working.pop(0)

        self._report.kept_count = len(working)
        result.extend(working)
        return result

    async def summarise(
        self,
        messages: list[Message | dict[str, Any]],
        summary_model: Any = None,
    ) -> str | None:
        """Try to summarise older messages.

        Args:
            messages: The messages to summarise.
            summary_model: A callable that accepts a prompt and returns text.

        Returns:
            A summary string, or None if summarisation failed.
        """
        if not messages or summary_model is None:
            return None

        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "user") if isinstance(msg, dict) else msg.role
            content = msg.get("content", "") if isinstance(msg, dict) else (msg.content or "")
            if content:
                lines.append(f"{role}: {content[:500]}")

        if not lines:
            return None

        prompt = (
            "Summarise the following conversation concisely, preserving all "
            "important facts, decisions, and context. Write a single paragraph:\n\n"
            + "\n".join(lines[-20:])
        )

        try:
            if callable(summary_model):
                result = await summary_model(prompt)
                summary = str(result).strip()
            else:
                _LOG.warning("summary_model is not callable, skipping summarisation")
                return None
        except Exception as exc:
            _LOG.warning("Context summarisation failed: %s", exc)
            return None

        if not summary:
            return None

        self._report.summary = summary
        return summary

    def compact(
        self,
        messages: list[dict[str, Any]],
        summary: str | None,
        *,
        preserve_count: int = 6,
    ) -> list[dict[str, Any]]:
        """Replace older messages with a summary, keeping recent ones."""
        if summary is None:
            cutoff = max(1, len(messages) - preserve_count)
            trimmed = messages[cutoff:]
            self._report.summarised_count = cutoff
            self._report.compacted = True
            _LOG.info("Context trimmed: dropped %d messages, kept %d", cutoff, len(trimmed))
            return trimmed

        cutoff = max(1, len(messages) - preserve_count)
        older = messages[:cutoff]
        newer = messages[cutoff:]

        result: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": f"[Previous conversation summarised]\n{summary}",
            }
        ]
        result.extend(newer)
        self._report.summarised_count = len(older)
        self._report.compacted = True
        _LOG.info(
            "Context compacted: summarised %d messages into one, kept %d recent",
            len(older), len(newer),
        )
        return result
