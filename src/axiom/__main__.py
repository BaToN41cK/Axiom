"""``python -m axiom`` / the ``axiom`` entry point.

The only place in the project where a frontend is selected:

    axiom                → frontends.tui      (Textual workspace)
    axiom --gui          → frontends.gui      (Tauri desktop app, desktop/)
"""

from __future__ import annotations

import sys

from axiom import __version__

_HELP = f"""AXIOM {__version__} — Local Intelligence Terminal Workspace

Usage:
  axiom                     Start the TUI workspace
  axiom --gui               Start the desktop GUI (Tauri app in desktop/)
  axiom --help              Show this help
  axiom --version           Show the version
"""


def main(argv: list[str] | None = None) -> int:
    """Dispatch to the selected frontend."""
    args = list(sys.argv[1:] if argv is None else argv)

    if any(arg in ("--help", "-h") for arg in args):
        print(_HELP)
        return 0
    if "--version" in args:
        print(f"AXIOM {__version__}")
        return 0

    if "--gui" in args:
        from axiom.frontends.gui.main import main as gui_main

        return gui_main()

    unknown = [a for a in args if a.startswith("-")]
    if unknown:
        print(f"Unknown option(s): {' '.join(unknown)}\n\n{_HELP}", file=sys.stderr)
        return 2

    from axiom.frontends.tui.app import main as tui_main

    return tui_main()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
