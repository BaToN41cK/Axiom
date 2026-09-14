"""Domain errors raised by the AXIOM core.

Every error that can reach a user is expressed as a subclass of
:class:`AxiomError` so that frontends can render clean messages instead of
tracebacks.
"""

from __future__ import annotations


class AxiomError(Exception):
    """Base class for all AXIOM domain errors."""

    #: short machine-readable kind, used by ErrorEvent
    kind: str = "error"

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class OllamaUnavailableError(AxiomError):
    """Ollama server could not be reached."""

    kind = "ollama_unavailable"


class ModelNotFoundError(AxiomError):
    """Requested model does not exist on the Ollama server."""

    kind = "model_not_found"


class InvalidResponseError(AxiomError):
    """Ollama returned a malformed / unexpected response."""

    kind = "invalid_response"


class GenerationCancelledError(AxiomError):
    """Generation was cancelled by the user."""

    kind = "cancelled"


class SearchUnavailableError(AxiomError):
    """Web search backend is unreachable or returned nothing usable."""

    kind = "search_unavailable"


class EmptyResponseError(AxiomError):
    """Model finished generation without producing usable content."""

    kind = "empty_response"


class InvalidTransitionError(AxiomError):
    """Illegal generation state transition (internal invariant broken)."""

    kind = "invalid_transition"
