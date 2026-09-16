"""AXIOM — Local Intelligence Terminal Workspace.

A premium terminal AI client powered by a local Ollama backend.

Public API surface. Frontends should depend only on what is exported here
and on :mod:`axiom.core` / :mod:`axiom.shared` modules.
"""

from axiom.core.chat import ChatSession
from axiom.core.config import Config
from axiom.core.errors import (
    AxiomError,
    GenerationCancelledError,
    InvalidResponseError,
    ModelNotFoundError,
    OllamaUnavailableError,
    SearchUnavailableError,
)
from axiom.core.events import (
    ChatEvent,
    ContentChunk,
    Done,
    ErrorEvent,
    Message,
    ReasoningChunk,
    SearchResultEvent,
    StatusChange,
    ToolCallEvent,
    ToolResultEvent,
)
from axiom.core.models import ModelInfo, ModelRegistry
from axiom.core.state import GenerationState
from axiom.core.state_machine import GenerationStateMachine

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # core
    "ChatSession",
    "Config",
    "GenerationState",
    "GenerationStateMachine",
    "Message",
    "ModelInfo",
    "ModelRegistry",
    # events
    "ChatEvent",
    "ContentChunk",
    "Done",
    "ErrorEvent",
    "ReasoningChunk",
    "SearchResultEvent",
    "StatusChange",
    "ToolCallEvent",
    "ToolResultEvent",
    # errors
    "AxiomError",
    "GenerationCancelledError",
    "InvalidResponseError",
    "ModelNotFoundError",
    "OllamaUnavailableError",
    "SearchUnavailableError",
]
