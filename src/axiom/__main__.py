"""``python -m axiom`` / the ``axiom`` entry point.

The only place in the project where a frontend is selected:

    axiom                → frontends.tui      (Textual workspace)
    axiom -p "hello"     → frontends.cli      (one-shot, pipe, --json)
    axiom --json ...     → frontends.cli
    echo "hi" | axiom    → frontends.cli      (stdin detected)
    axiom --gui          → frontends.gui      (Tkinter GUI window)
"""

from __future__ import annotations

import sys

from axiom import __version__

#: Flags that unambiguously request the non-interactive CLI frontend.
_CLI_FLAGS = {
    "-p",
    "--prompt",
    "--json",
    "--list-models",
    "--ollama-url",
    "--think",
    "--search",
    "--no-search",
    "--show-reasoning",
    "-m",
    "--model",
}

_HELP = f"""AXIOM {__version__} — Local Intelligence Terminal Workspace

Usage:
  axiom                     Start the TUI workspace
  axiom -p "question"       One-shot answer on stdout (CLI frontend)
  echo "question" | axiom   Pipe mode
  axiom --json -p "…"       NDJSON event stream
  axiom --list-models       List models detected in Ollama
  axiom --gui               GUI window (Tkinter)
  axiom --help              Show this help
  axiom --version           Show the version
"""


def _wants_cli(argv: list[str]) -> bool:
    if any(arg in _CLI_FLAGS for arg in argv):
        return True
    if any(arg.startswith(("--prompt=", "--model=", "--ollama-url=", "--think=")) for arg in argv):
        return True
    # piped input means the user wants a one-shot answer
    try:
        return not sys.stdin.isatty()
    except (ValueError, OSError, AttributeError):
        return False


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
        from axiom.frontends.gui import available

        if not available():
            print(
                "The GUI frontend requires tkinter, which is missing from this "
                "Python build.\nUse the TUI (`axiom`) or the CLI (`axiom -p \"...\").",
                file=sys.stderr,
            )
            return 2

        from axiom.frontends.gui.app import main as gui_main

        return gui_main()

    if _wants_cli(args):
        from axiom.frontends.cli.main import main as cli_main

        return cli_main(args)

    from axiom.frontends.tui.app import main as tui_main

    return tui_main()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
