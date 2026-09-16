"""Shared layer — visual identity and pure formatting helpers.

Contains only data and pure functions: no state, no backend access, and no
imports from ``axiom.core`` or any UI framework.
"""

from axiom.shared import formatting, logo, theme

__all__ = ["formatting", "logo", "theme"]
