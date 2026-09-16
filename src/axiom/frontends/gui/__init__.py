"""GUI frontend — a Tkinter adapter over the AXIOM core (no new dependencies).

The shipped application lives in :mod:`axiom.frontends.gui.app` (run it with
``axiom --gui``). This module also keeps the :class:`GuiBackend` protocol —
the *contract* any other graphical toolkit (Qt/Toga/web) must satisfy to
render :data:`axiom.core.events.ChatEvent` without touching ``axiom.core``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from axiom.core.chat import ChatSession
from axiom.core.events import ChatEvent
from axiom.core.models import ModelInfo

__all__ = ["GuiBackend", "available", "create_backend"]


class GuiBackend(Protocol):
    """The minimal contract any graphical frontend must satisfy."""

    def __init__(self, session: ChatSession) -> None: ...

    async def startup(self) -> list[ModelInfo]:
        """Return the models reported by the backend (real discovery)."""
        ...

    def send(self, text: str, *, force_search: bool = False) -> AsyncIterator[ChatEvent]:
        """Stream core events for one user message."""
        ...

    def cancel(self) -> bool:
        """Cancel the in-flight generation."""
        ...


def available() -> bool:
    """Whether the GUI can run here (Tkinter must be importable)."""
    try:
        import tkinter  # noqa: F401

        return True
    except ImportError:
        return False


def create_backend(session: ChatSession) -> GuiBackend:
    """Headless GUI backends for embedding are not bundled yet.

    Run the interactive application with ``axiom --gui`` (Tkinter, see
    :mod:`axiom.frontends.gui.app`), or implement :class:`GuiBackend` on top
    of ``axiom.core.events`` for another toolkit.
    """
    raise NotImplementedError(
        "No headless GUI backend is bundled. Run `axiom --gui` for the Tkinter "
        "application, or implement axiom.frontends.gui.GuiBackend on top of "
        "axiom.core.events."
    )
