"""State machine transition tests."""

from __future__ import annotations

import pytest

from axiom.core.errors import InvalidTransitionError
from axiom.core.state import GenerationState
from axiom.core.state_machine import GenerationStateMachine


def test_initial_state_is_idle():
    assert GenerationStateMachine().state is GenerationState.IDLE


def test_valid_idle_to_busy_transitions():
    for target in (
        GenerationState.CONNECTING,
        GenerationState.THINKING,
        GenerationState.SEARCHING,
        GenerationState.TOOL_CALL,
        GenerationState.RECEIVING,
    ):
        machine = GenerationStateMachine()
        machine.transition(target)
        assert machine.state is target


def test_busy_states_can_move_between_each_other():
    machine = GenerationStateMachine()
    machine.transition(GenerationState.CONNECTING)
    machine.transition(GenerationState.THINKING)
    machine.transition(GenerationState.RECEIVING)
    machine.transition(GenerationState.THINKING)
    assert machine.state is GenerationState.THINKING


def test_busy_state_reaches_final():
    for final in (
        GenerationState.COMPLETED,
        GenerationState.CANCELLED,
        GenerationState.ERROR,
    ):
        machine = GenerationStateMachine()
        machine.transition(GenerationState.RECEIVING)
        machine.transition(final)
        assert machine.state is final
        assert machine.state.is_final


def test_final_state_requires_reset_before_new_cycle():
    machine = GenerationStateMachine()
    machine.transition(GenerationState.RECEIVING)
    machine.transition(GenerationState.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        machine.transition(GenerationState.CONNECTING)
    machine.reset()
    assert machine.state is GenerationState.IDLE
    machine.transition(GenerationState.CONNECTING)
    assert machine.state is GenerationState.CONNECTING


def test_transition_to_same_state_is_noop():
    machine = GenerationStateMachine()
    machine.transition(GenerationState.IDLE)
    assert machine.state is GenerationState.IDLE


def test_reset_from_busy_returns_to_idle():
    machine = GenerationStateMachine()
    machine.transition(GenerationState.THINKING)
    machine.reset()
    assert machine.state is GenerationState.IDLE
