"""AXIOM status tracking and display."""

import time
from dataclasses import dataclass, field
from typing import Optional

from rich.text import Text

from src.ui.theme import SYMBOLS, STATUS_COLORS


@dataclass
class TaskStatus:
    """Tracks the status of a single task/response."""

    # Timing
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    # Status flags
    thinking: bool = False
    thinking_start: float = 0.0
    thinking_duration: float = 0.0

    planning: bool = False
    planning_start: float = 0.0
    planning_duration: float = 0.0

    generating: bool = False
    generating_start: float = 0.0

    # Counters
    search_count: int = 0
    source_count: int = 0
    tool_count: int = 0
    token_count: int = 0

    # Context
    prompt_tokens: int = 0
    context_window: int = 32768

    # State
    current_state: str = "ready"
    cancelled: bool = False

    # Sources
    sources: list = field(default_factory=list)

    def start_thinking(self):
        """Mark thinking as started."""
        self.thinking = True
        self.thinking_start = time.time()
        self.current_state = "thinking"

    def stop_thinking(self):
        """Mark thinking as completed."""
        if self.thinking_start > 0:
            self.thinking_duration = time.time() - self.thinking_start
        self.thinking = False
        self.thinking_start = 0

    def start_planning(self):
        """Mark planning as started."""
        self.planning = True
        self.planning_start = time.time()
        self.current_state = "planning"

    def stop_planning(self):
        """Mark planning as completed."""
        if self.planning_start > 0:
            self.planning_duration = time.time() - self.planning_start
        self.planning = False
        self.planning_start = 0

    def start_generating(self):
        """Mark generation as started."""
        self.generating = True
        self.generating_start = time.time()
        self.current_state = "generating"

    def stop_generating(self):
        """Mark generation as completed."""
        self.generating = False
        self.generating_start = 0

    def add_search(self, count: int = 1):
        """Add search count."""
        self.search_count += count
        self.tool_count += 1

    def add_sources(self, sources: list):
        """Add sources."""
        self.sources.extend(sources)
        self.source_count = len(self.sources)
        self.tool_count += 1

    def set_tokens(self, count: int):
        """Set token count."""
        self.token_count = count

    def set_prompt_tokens(self, count: int):
        """Set prompt token count for context calculation."""
        self.prompt_tokens = count

    @property
    def context_percentage(self) -> int:
        """Calculate context usage percentage."""
        if self.context_window <= 0:
            return 0
        return min(100, int((self.prompt_tokens / self.context_window) * 100))

    @property
    def is_active(self) -> bool:
        """Check if task is currently active."""
        return self.thinking or self.planning or self.generating

    def cancel(self):
        """Cancel the current task."""
        self.cancelled = True
        self.thinking = False
        self.planning = False
        self.generating = False

    def finalize(self):
        """Mark task as complete."""
        self.end_time = time.time()
        self.thinking = False
        self.planning = False
        self.generating = False
        self.current_state = "ready"

    def render_status_lines(self) -> Text:
        """Render completed status lines."""
        text = Text()

        if self.thinking_duration > 0:
            text.append(
                f"  {SYMBOLS['success']} Thinking{'':<18}"
                f"{self.thinking_duration:.1f}s\n",
                style="status.success",
            )

        if self.planning_duration > 0:
            text.append(
                f"  {SYMBOLS['success']} Planning{'':<18}"
                f"{self.planning_duration:.1f}s\n",
                style="status.success",
            )

        if self.search_count > 0:
            text.append(
                f"  {SYMBOLS['success']} Search{'':<20}"
                f"{self.search_count} results\n",
                style="status.success",
            )

        if self.source_count > 0:
            text.append(
                f"  {SYMBOLS['success']} Web Research{'':<13}"
                f"{self.source_count} sources\n",
                style="status.success",
            )

        return text

    def render_active_status(self) -> Text:
        """Render current active status."""
        text = Text()

        if self.thinking:
            elapsed = time.time() - self.thinking_start
            text.append(
                f"  {SYMBOLS['active']} Thinking...{'':<16}"
                f"{elapsed:.1f}s\n",
                style="status.active",
            )
        elif self.planning:
            elapsed = time.time() - self.planning_start
            text.append(
                f"  {SYMBOLS['active']} Planning...{'':<16}"
                f"{elapsed:.1f}s\n",
                style="status.active",
            )
        elif self.generating:
            text.append(
                f"  {SYMBOLS['active']} Generating...\n",
                style="status.active",
            )

        return text

    def render_final_state(self, success: bool = True, message: str = "") -> Text:
        """Render the final task state."""
        text = Text()
        text.append("\n")
        if success:
            text.append(f"  {SYMBOLS['success']} {message or 'Answer completed'}\n", style="status.success")
        else:
            text.append(f"  {SYMBOLS['error']} {message or 'Task failed'}\n", style="status.error")
        return text
