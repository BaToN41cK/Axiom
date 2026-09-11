"""AXIOM session management — history, statistics, context."""

from dataclasses import dataclass, field
from typing import Any, Optional

from src.config import config
from src.utils import format_number


@dataclass
class Message:
    """A single message in the conversation."""
    role: str  # system, user, assistant, tool
    content: str
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass
class Session:
    """Manages the current conversation session."""

    messages: list[Message] = field(default_factory=list)
    system_prompt: str = ""

    # Statistics
    total_tokens: int = 0
    total_searches: int = 0
    total_sources: int = 0
    total_tools: int = 0
    prompt_tokens: int = 0

    # Context
    context_window: int = 32768

    def __post_init__(self):
        """Initialize with system prompt."""
        if not self.system_prompt:
            self.system_prompt = self._default_system_prompt()
        # Add system message
        if self.messages and self.messages[0].role != "system":
            self.messages.insert(0, Message(role="system", content=self.system_prompt))
        elif not self.messages:
            self.messages.append(Message(role="system", content=self.system_prompt))

    def _default_system_prompt(self) -> str:
        """Generate default system prompt."""
        return (
            "You are AXIOM, a local AI assistant running in a terminal.\n\n"
            "You have access to web search and web fetch tools.\n"
            "Use them when the user asks about current events, recent information, "
            "or when you need to verify facts.\n\n"
            "Be concise, helpful, and direct.\n"
            "Format responses using Markdown when appropriate.\n"
            "Always cite sources when using web search results."
        )

    def add_user_message(self, content: str):
        """Add a user message."""
        self.messages.append(Message(role="user", content=content))

    def add_assistant_message(self, content: str, tool_calls: Optional[list] = None):
        """Add an assistant message."""
        self.messages.append(Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
        ))

    def add_tool_result(self, tool_call_id: str, name: str, content: str):
        """Add a tool result message."""
        self.messages.append(Message(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            name=name,
        ))

    def get_messages_for_api(self) -> list[dict[str, Any]]:
        """Get messages formatted for the Ollama API.

        Ollama expects a minimal format: assistant tool_calls contain only
        {"function": {...}}, and tool result messages carry role + content.
        Extra OpenAI-style fields (id, tool_call_id, name) are stripped.
        """
        result: list[dict[str, Any]] = []
        for msg in self.messages:
            api_msg: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                api_msg["tool_calls"] = [
                    {"function": tc["function"]} for tc in msg.tool_calls
                ]
            result.append(api_msg)
        return result

    def update_tokens(self, eval_count: int = 0, prompt_eval_count: int = 0):
        """Update token statistics."""
        self.total_tokens += eval_count
        self.prompt_tokens = prompt_eval_count

    def add_search(self, count: int = 1):
        """Add search count."""
        self.total_searches += count

    def add_sources(self, count: int = 1):
        """Add source count."""
        self.total_sources += count

    def add_tool_use(self, count: int = 1):
        """Add tool use count."""
        self.total_tools += count

    @property
    def context_percentage(self) -> int:
        """Calculate context usage percentage."""
        if self.context_window <= 0:
            return 0
        return min(100, int((self.prompt_tokens / self.context_window) * 100))

    @property
    def formatted_tokens(self) -> str:
        """Get formatted token count."""
        return format_number(self.total_tokens)

    def clear(self):
        """Clear session history but keep system prompt."""
        self.messages = [Message(role="system", content=self.system_prompt)]
        self.total_tokens = 0
        self.total_searches = 0
        self.total_sources = 0
        self.total_tools = 0
        self.prompt_tokens = 0

    def trim_context(self, max_messages: int = 50):
        """Trim context to last N messages (keeping system prompt)."""
        if len(self.messages) > max_messages:
            system = self.messages[0] if self.messages[0].role == "system" else None
            self.messages = self.messages[-max_messages:]
            if system and self.messages[0].role != "system":
                self.messages.insert(0, system)
