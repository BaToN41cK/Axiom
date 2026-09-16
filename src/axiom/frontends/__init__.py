"""Frontends — thin adapters that consume the CORE event stream.

Frontends depend on ``axiom.core`` and ``axiom.shared`` only, and never on each
other:

* ``tui``  — Textual terminal workspace (default).
* ``cli``  — one-shot / pipe / ``--json`` adapter for scripts.
* ``gui``  — reserved slot; ships the event contract but no implementation yet.

Nothing is imported here on purpose: ``import axiom.frontends`` must stay cheap
and must not pull a UI toolkit into the process (the CLI never needs Textual).
"""

from __future__ import annotations
