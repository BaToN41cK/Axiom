"""TUI widgets — every widget is a projection of real core state.

* ``commands``  — slash-command data plus the ``/`` autocomplete menu.
* ``header``    — identity bar and the live status bar.
* ``messages``  — user/assistant turns and the scrolling conversation.
* ``panels``    — modal panels (models, history, settings, help, status).
* ``prompt``    — the multiline input bar with its Stop control.
* ``reasoning`` — streaming text and the collapsible thinking block.
* ``search``    — the web-search block with clickable sources.
* ``splash``    — the animated startup screen running real probes.

Submodules are imported explicitly by :mod:`axiom.frontends.tui.app`, so this
package intentionally re-exports nothing (importing a widget must never be a
side effect of importing the package).
"""

from __future__ import annotations
