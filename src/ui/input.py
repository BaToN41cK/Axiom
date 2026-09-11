"""AXIOM keyboard input — line editor with history navigation.

Terminal-first input: plain prompt, echo, Backspace, Up/Down history,
Ctrl+C abort, Ctrl+L clear. Uses msvcrt on Windows and falls back to
a standard input() prompt elsewhere.
"""

import sys
from typing import Callable, Optional


class InputReader:
    """Reads a line of input with ↑/↓ history and Ctrl+L support."""

    def __init__(self, on_clear: Optional[Callable[[], None]] = None):
        self.history: list[str] = []
        self.on_clear = on_clear
        self._index = 0

    def add(self, line: str):
        """Add a submitted line to history."""
        if line.strip():
            self.history.append(line.strip())
        self._index = len(self.history)

    def read(self, prompt: str = " > ") -> str:
        """Read one line. Raises KeyboardInterrupt on Ctrl+C."""
        if sys.platform == "win32":
            return self._read_windows(prompt)
        # Fallback for non-Windows terminals.
        return input(prompt)

    # -- Windows implementation -------------------------------------------

    def _redraw(self, prompt: str, line: str):
        sys.stdout.write("\r" + prompt + line + " \r" + prompt + line)
        sys.stdout.flush()

    def _read_windows(self, prompt: str) -> str:
        import msvcrt

        line = ""
        self._index = len(self.history)
        sys.stdout.write(prompt)
        sys.stdout.flush()

        while True:
            ch = msvcrt.getwch()

            if ch in ("\x00", "\xe0"):  # function / arrow key prefix
                code = msvcrt.getwch()
                if code == "H":  # Up
                    if self.history and self._index > 0:
                        self._index -= 1
                        line = self.history[self._index]
                        self._redraw(prompt, line)
                elif code == "P":  # Down
                    if self._index < len(self.history) - 1:
                        self._index += 1
                        line = self.history[self._index]
                    else:
                        self._index = len(self.history)
                        line = ""
                    self._redraw(prompt, line)
                continue

            if ch == "\r":  # Enter
                sys.stdout.write("\n")
                sys.stdout.flush()
                return line

            if ch in ("\x08", "\x7f"):  # Backspace
                if line:
                    line = line[:-1]
                    sys.stdout.write("\r" + prompt + line + " \r" + prompt + line)
                    sys.stdout.flush()
                continue

            if ch == "\x03":  # Ctrl+C
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise KeyboardInterrupt

            if ch == "\x0c":  # Ctrl+L — clear terminal
                if self.on_clear:
                    self.on_clear()
                sys.stdout.write(prompt + line)
                sys.stdout.flush()
                continue

            if ch == "\x1b":  # Esc — clear current line
                line = ""
                sys.stdout.write("\r" + prompt + " " * 40 + "\r" + prompt)
                sys.stdout.flush()
                continue

            if ch >= " " or ch == "\t":
                line += ch
                sys.stdout.write(ch)
                sys.stdout.flush()