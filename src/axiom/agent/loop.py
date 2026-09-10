"""Core agent loop: model-driven tool use with cancellation and budgets.

This is the heart of Axiom: the model decides actions; the loop only
enforces permissions, budgets and error recovery. No scripted workflows.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from axiom.agent.context import ContextManager
from axiom.core.errors import ProviderError, ProviderRateLimitError
from axiom.core.logging import get_logger
from axiom.core.types import AgentStatus, ToolCall, ToolResult
from axiom.models.provider import ModelProvider, ToolSpec
from axiom.permissions.manager import PermissionManager
from axiom.tools.registry import ToolContext, ToolRegistry

logger = get_logger("agent_loop")

SYSTEM_TEMPLATE = """You are Axiom, a terminal-first AI coding agent working in the workspace: {workspace}

Project context:
{project}

Security mode: {security_mode}. Respect tool permissions; if a tool returns a
permission error, do not retry the same action.

Guidelines:
- Inspect before editing: read files before changing them.
- Make precise edits (edit_file), avoid rewriting whole files.
- After code changes, run the project's tests when a test framework exists.
- When the task is complete, reply with a short final summary (no tool calls).
- Use tools for facts; never invent file contents or command output.
"""


@dataclass
class LoopConfig:
    max_iterations: int = 30
    iteration_timeout: float = 300.0
    max_consecutive_errors: int = 3
    temperature: float = 0.2
    max_tokens: int | None = None
    mode: str = "BUILD"


@dataclass
class LoopResult:
    status: AgentStatus
    final_text: str = ""
    iterations: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration: float = 0.0
    error: str = ""


class CancelledError(Exception):
    """Raised when the user cancels the loop (Ctrl+C)."""


class AgentLoop:
    """Model-driven execution loop."""

    def __init__(
        self,
        provider: ModelProvider,
        registry: ToolRegistry,
        tool_context: ToolContext,
        permission_manager: PermissionManager,
        context: ContextManager | None = None,
        config: LoopConfig | None = None,
        project_summary: str = "",
        on_event: Any = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.tool_context = tool_context
        self.permissions = permission_manager
        self.context = context or ContextManager()
        self.config = config or LoopConfig()
        self.project_summary = project_summary
        self._on_event = on_event
        self._cancelled = asyncio.Event()
        self.status = AgentStatus.IDLE
        self.last_message: str = ""

    # -- control -----------------------------------------------------------
    def cancel(self) -> None:
        """Request cancellation (Ctrl+C handler calls this)."""
        self._cancelled.set()

    def emit(self, event_type: str, **data: Any) -> None:
        if data.get("text"):
            self.last_message = str(data["text"])
        if self._on_event:
            try:
                self._on_event(event_type, data)
            except Exception:  # noqa: BLE001
                pass

    def _system_prompt(self) -> str:
        return SYSTEM_TEMPLATE.format(
            workspace=self.tool_context.workspace,
            project=self.project_summary or "(unknown project)",
            security_mode=self.permissions.security_mode,
        )

    # -- main loop -----------------------------------------------------------
    async def run(self, task: str) -> LoopResult:
        """Execute the task to completion. Returns a LoopResult."""
        start = time.monotonic()
        self.status = AgentStatus.PLANNING
        self.emit("task_start", task=task, mode=self.config.mode)
        system = self._system_prompt()
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        tools = [
            ToolSpec(name=t.name, description=t.description, parameters=t.parameters)
            for t in self.registry.list_tools()
        ]
        result = LoopResult(status=AgentStatus.FAILED)
        consecutive_errors = 0

        try:
            for iteration in range(1, self.config.max_iterations + 1):
                if self._cancelled.is_set():
                    result.status = AgentStatus.CANCELLED
                    result.error = "cancelled by user"
                    break
                result.iterations = iteration
                self.emit("iteration", iteration=iteration)

                response = await self._chat_with_recovery(messages, tools, system)
                if response.usage:
                    result.input_tokens += response.usage.input_tokens
                    result.output_tokens += response.usage.output_tokens

                if response.content:
                    self.emit("assistant", text=response.content)

                if response.tool_calls:
                    messages.append({
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": response.tool_calls,
                    })
                    self.status = AgentStatus.EXECUTING
                    all_denied = True
                    for call in response.tool_calls:
                        if self._cancelled.is_set():
                            result.status = AgentStatus.CANCELLED
                            break
                        tool_result = await self._execute_tool(call)
                        result.tool_calls += 1
                        if not tool_result.is_error or "permission denied" not in tool_result.content:
                            all_denied = False
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call.get("id", "call_0"),
                            "name": call.get("name", ""),
                            "content": tool_result.content,
                        })
                        self.emit("tool_result", name=call.get("name"),
                                  is_error=tool_result.is_error,
                                  content=tool_result.content[:400])
                    if result.status == AgentStatus.CANCELLED:
                        break
                    if all_denied:
                        consecutive_errors += 1
                        if consecutive_errors >= self.config.max_consecutive_errors:
                            result.error = "stopped: all tool calls denied by permissions"
                            break
                    else:
                        consecutive_errors = 0
                else:
                    result.status = AgentStatus.COMPLETE
                    result.final_text = response.content
                    self.last_message = response.content
                    break
            else:
                result.error = f"max iterations ({self.config.max_iterations}) reached"
        except CancelledError:
            result.status = AgentStatus.CANCELLED
            result.error = "cancelled"
        except ProviderError as exc:
            result.error = f"provider error: {exc.message}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent loop crashed")
            result.error = f"unexpected error: {exc}"

        result.duration = time.monotonic() - start
        self.emit("task_end", status=result.status.value, error=result.error)
        return result

    # -- helpers -----------------------------------------------------------
    async def _chat_with_recovery(self, messages, tools, system):
        """Call provider with rate-limit backoff and cancellation support."""
        delay = 1.0
        for _attempt in range(4):
            if self._cancelled.is_set():
                raise CancelledError()
            try:
                return await self.provider.chat(
                    messages=messages,
                    tools=tools,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    system=system,
                )
            except ProviderRateLimitError:
                self.emit("warning", text=f"Rate limited; retrying in {delay:.0f}s")
                await asyncio.sleep(delay)
                delay *= 2
        raise ProviderRateLimitError("rate limit persists after retries")

    async def _execute_tool(self, call: dict[str, Any]) -> ToolResult:
        arguments = call.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"_raw": arguments}
        tool_call = ToolCall(
            id=call.get("id", "call_0"), name=call.get("name", ""), arguments=arguments
        )
        return await self.registry.execute(tool_call, self.tool_context)

        self.permissions = permission_manager
        self.context = context or ContextManager()
        self.config = config or LoopConfig()
        self.project_summary = project_summary
        self._on_event = on_event
        self._cancelled = asyncio.Event()
        self.status = AgentStatus.IDLE
        self.last_message: str = ""

    # -- control -----------------------------------------------------------
    def cancel(self) -> None:
        """Request cancellation (Ctrl+C handler calls this)."""
        self._cancelled.set()

    def emit(self, event_type: str, **data: Any) -> None:
        if data.get("text"):
            self.last_message = str(data["text"])
        if self._on_event:
            try:
                self._on_event(event_type, data)
            except Exception:  # noqa: BLE001
                pass
