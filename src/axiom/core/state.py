"""Generation states of the AXIOM engine.

``GenerationState`` describes the *real* state of the backend — never a
cosmetic placeholder. UI statuses must only ever be projections of it.
"""

from __future__ import annotations

from enum import Enum


class GenerationState(str, Enum):
    """States of a single generation cycle."""

    IDLE = "idle"
    CONNECTING = "connecting"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    SEARCHING = "searching"
    RECEIVING = "receiving"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"

    @property
    def is_final(self) -> bool:
        """Terminal states of one generation cycle."""
        return self in (GenerationState.COMPLETED, GenerationState.CANCELLED, GenerationState.ERROR)

    @property
    def is_busy(self) -> bool:
        """States in which a generation is actually in flight."""
        return self not in (
            GenerationState.IDLE,
            GenerationState.COMPLETED,
            GenerationState.CANCELLED,
            GenerationState.ERROR,
        )

    @property
    def label(self) -> str:
        """Human readable label used by frontends."""
        return {
            GenerationState.IDLE: "Idle",
            GenerationState.CONNECTING: "Connecting",
            GenerationState.THINKING: "Thinking",
            GenerationState.TOOL_CALL: "Tool",
            GenerationState.SEARCHING: "Searching",
            GenerationState.RECEIVING: "Generating",
            GenerationState.COMPLETED: "Completed",
            GenerationState.CANCELLED: "Cancelled",
            GenerationState.ERROR: "Failed",
        }[self]
