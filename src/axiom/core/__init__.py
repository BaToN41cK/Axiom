"""Frontend-agnostic core of AXIOM.

This package MUST NOT import any UI framework (textual, rich, PyQt, toga...).
It communicates with frontends exclusively through methods and an event stream
(see :mod:`axiom.core.events`).
"""
