"""Frontends — thin adapters that consume the CORE event stream.

Frontends depend on ``axiom.core`` and ``axiom.shared`` only, and never on each
other:

* ``tui``  — Textual terminal workspace (default).
* ``gui``  — Tauri desktop launcher (``axiom --gui``, app lives in ``desktop/``).

Nothing is imported here on purpose: ``import axiom.frontends`` must stay cheap
and must not pull a UI toolkit into the process.
"""

from __future__ import annotations
