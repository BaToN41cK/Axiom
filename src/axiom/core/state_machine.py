"""Explicit state machine for a generation cycle.

Guards against inconsistent UI: e.g. showing ``COMPLETED`` while a stream is
still open, or emitting ``THINKING`` after ``COMPLETED``. All transitions are
validated here; the agent loop uses this as the single source of truth.
"""

from __future__ import annotations

from axiom.core.errors import InvalidTransitionError
from axiom.core.state import GenerationState

#: Legal transitions of one generation cycle.
VALID_TRANSITIONS: dict[GenerationState, set[GenerationState]] = {
    GenerationState.IDLE: {
        GenerationState.CONNECTING,
        GenerationState.THINKING,
        GenerationState.SEARCHING,
        GenerationState.TOOL_CALL,
        GenerationState.RECEIVING,
    },
    GenerationState.CONNECTING: {
        GenerationState.THINKING,
        GenerationState.SEARCHING,
        GenerationState.TOOL_CALL,
        GenerationState.RECEIVING,
    },
    GenerationState.THINKING: {
        GenerationState.RECEIVING,
        GenerationState.TOOL_CALL,
        GenerationState.SEARCHING,
        GenerationState.CONNECTING,
    },
    GenerationState.SEARCHING: {
        GenerationState.TOOL_CALL,
        GenerationState.THINKING,
        GenerationState.RECEIVING,
        GenerationState.CONNECTING,
    },
    GenerationState.TOOL_CALL: {
        GenerationState.SEARCHING,
        GenerationState.THINKING,
        GenerationState.RECEIVING,
        GenerationState.CONNECTING,
    },
    GenerationState.RECEIVING: {
        GenerationState.THINKING,
        GenerationState.TOOL_CALL,
        GenerationState.SEARCHING,
        GenerationState.CONNECTING,
    },
}

#: Final states every busy state may resolve to.
_FINAL = {
    GenerationState.COMPLETED,
    GenerationState.CANCELLED,
    GenerationState.ERROR,
}


class GenerationStateMachine:
    """Tracks and validates the state of one chat session."""

    def __init__(self) -> None:
        self._state = GenerationState.IDLE

    @property
    def state(self) -> GenerationState:
        return self._state

    def can(self, target: GenerationState) -> bool:
        """Whether a transition to *target* is legal right now."""
        if target is self._state:
            return True
        if self._state.is_final:
            # a finished cycle must be reset before a new one starts
            return target is GenerationState.IDLE
        if self._state is GenerationState.IDLE:
            return target in VALID_TRANSITIONS[GenerationState.IDLE] or target in _FINAL
        return target in VALID_TRANSITIONS.get(self._state, set()) or target in _FINAL

    def transition(self, target: GenerationState) -> GenerationState:
        """Move to *target*.

        Raises:
            InvalidTransitionError: if the transition is illegal. Final states
                must first be reset via :meth:`reset`.
        """
        if target is self._state:
            return self._state
        if not self.can(target):
            raise InvalidTransitionError(
                f"Illegal generation state transition: {self._state.value} -> {target.value}"
            )
        prev, self._state = self._state, target
        return prev

    def reset(self) -> None:
        """Return to IDLE (legal from any final or busy state on new send)."""
        self._state = GenerationState.IDLE
