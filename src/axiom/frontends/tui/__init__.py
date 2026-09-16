"""TUI frontend — a thin Textual adapter over the AXIOM core.

This package must never be imported by ``axiom.core``; it only consumes the
core's event stream and calls its commands.
"""

from axiom.frontends.tui.app import AxiomApp, main

__all__ = ["AxiomApp", "main"]
