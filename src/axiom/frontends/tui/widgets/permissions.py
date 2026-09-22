"""Permission dialog — ask the user to approve or deny a tool execution.

This is the TUI's implementation of the ``request_callback`` that
:class:`~axiom.core.permissions.PermissionManager` calls when the current
mode requires user confirmation.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from axiom.shared import theme


class PermissionDialog(ModalScreen[bool]):
    """Modal dialog showing tool details and asking Approve / Deny.

    Returns ``True`` when the user approves, ``False`` when denied.
    """

    BINDINGS = [
        Binding("escape", "deny", "Deny", show=True),
        Binding("f1", "approve", "Approve", show=True),
        Binding("enter", "approve", "Approve", show=False),
    ]

    def __init__(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._tool_args = tool_args

    def compose(self) -> ComposeResult:
        yield Static("", id="perm-overlay")
        with Vertical(id="perm-dialog"):
            yield Static("PERMISSION REQUIRED", id="perm-title")
            yield Static(f"Tool:  {theme.TOOL_GLYPH} {self._tool_name}", id="perm-tool", markup=False)
            if self._tool_args:
                args_text = "\n".join(
                    f"  {key} = {value}"
                    for key, value in self._tool_args.items()
                )
                yield Static(f"Arguments:\n{args_text}", id="perm-args", markup=False)
            yield Static(
                "Allow this tool to execute?",
                id="perm-prompt",
                markup=False,
            )
            with Horizontal(id="perm-buttons"):
                yield Button("Approve", id="perm-approve", variant="primary")
                yield Button("Deny", id="perm-deny", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "perm-approve":
            self.dismiss(True)
        elif event.button.id == "perm-deny":
            self.dismiss(False)

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)
