"""AXIOM Agent — orchestrates Ollama, tools, and streaming."""

import json
from typing import Optional

from src.config import config
from src.ollama import OllamaClient
from src.web_tools import WebSearchTool, get_tool_definitions, execute_tool
from src.session import Session
from src.ui.status import TaskStatus


class Agent:
    """Main agent that orchestrates AI responses with tool use."""

    def __init__(self, session: Session, model: str = ""):
        self.session = session
        self.model = model or config.model
        self.ollama = OllamaClient(model=self.model)
        self.web = WebSearchTool()
        self.status = TaskStatus(context_window=config.context_window)
        self._cancelled = False
        self._iteration = 0

    async def close(self):
        """Close connections."""
        await self.ollama.close()

    def cancel(self):
        """Cancel current operation."""
        self._cancelled = True
        self.status.cancel()

    async def _stream_response(self, messages, tools, on_token=None, on_status=None):
        """Stream a single response from Ollama.
        
        Returns tuple of (content, thinking, tool_calls).
        
        Status events emitted via on_status(event, started):
            "thinking"   — first-pass model reasoning (iteration 1)
            "reasoning"  — synthesis reasoning after tool results (iteration 2+)
            "planning"   — the model has decided to use tools
            "generating" — final answer text is streaming
        """
        thinking_text = ""
        content_text = ""
        tool_calls = []
        # In later iterations (after tool results) reasoning is "reasoning".
        think_event = "thinking" if self._iteration <= 1 else "reasoning"

        async for chunk in self.ollama.chat_stream(messages, tools=tools):
            if self._cancelled:
                break

            msg = chunk.get("message", {})
            content = msg.get("content", "")
            thinking = msg.get("thinking", "")
            chunk_tool_calls = msg.get("tool_calls", [])

            # Handle thinking
            if thinking and not thinking_text:
                self.status.start_thinking()
                if on_status:
                    on_status(think_event, True)

            if thinking:
                thinking_text += thinking
                if on_token:
                    on_token(thinking, is_thinking=True)

            # Handle content
            if content:
                if thinking_text and self.status.thinking:
                    self.status.stop_thinking()
                    if on_status:
                        on_status(think_event, False)

                if not self.status.generating:
                    self.status.start_generating()
                    if on_status:
                        on_status("generating", True)

                content_text += content
                if on_token:
                    on_token(content, is_thinking=False)

            # Handle tool calls — the model has planned to use tools
            if chunk_tool_calls:
                if not self.status.planning:
                    self.status.start_planning()
                    if on_status:
                        on_status("planning", True)
                tool_calls.extend(chunk_tool_calls)

            # Check if done
            if chunk.get("done", False):
                if self.status.thinking:
                    self.status.stop_thinking()
                    if on_status:
                        on_status(think_event, False)
                if self.status.planning:
                    self.status.stop_planning()
                    if on_status:
                        on_status("planning", False)
                if self.status.generating:
                    self.status.stop_generating()
                    if on_status:
                        on_status("generating", False)

                eval_count = chunk.get("eval_count", 0)
                prompt_eval_count = chunk.get("prompt_eval_count", 0)
                self.status.set_tokens(eval_count)
                self.status.set_prompt_tokens(prompt_eval_count)
                self.session.update_tokens(eval_count, prompt_eval_count)
                break

        return content_text, thinking_text, tool_calls

    def _normalize_tool_calls(self, tool_calls) -> list[dict]:
        """Normalize raw tool calls into the OpenAI-style dict format."""
        normalized = []
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            normalized.append({
                "id": tc.get("id", ""),
                "type": "function",
                "function": {"name": name, "arguments": args},
            })
        return normalized

    async def _execute_tools(self, tool_calls, on_tool=None):
        """Execute normalized tool calls and add results to the session."""
        for tc in tool_calls:
            if self._cancelled:
                break

            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})
            tc_id = tc.get("id", "")

            # Notify tool execution started
            if on_tool:
                on_tool(name, args, True, None)

            # Execute the tool
            result = await execute_tool(name, args, self.web)

            # Update status counters
            if name == "web_search":
                self.status.add_search(result.get("count", 0))
                self.session.add_search(result.get("count", 0))
            elif name == "web_fetch":
                self.status.add_sources([result])
                self.session.add_sources(1)

            self.session.add_tool_use(1)

            # Notify tool complete
            if on_tool:
                on_tool(name, args, False, result)

            # Add tool result to session
            result_content = json.dumps(result, ensure_ascii=False) if result else "{}"
            self.session.add_tool_result(tc_id, name, result_content)

    async def process_message(
        self,
        user_message: str,
        on_token=None,
        on_status=None,
        on_tool=None,
    ) -> dict:
        """Process a user message and generate a response.
        
        Args:
            user_message: The user's input message.
            on_token: Callback for each token received.
            on_status: Callback for status updates.
            on_tool: Callback for tool execution.
            
        Returns:
            Dict with success, content, and statistics.
        """
        self._cancelled = False
        self.status = TaskStatus(context_window=config.context_window)

        # Add user message to session
        self.session.add_user_message(user_message)

        # Build messages for API
        messages = self.session.get_messages_for_api()

        # Get tool definitions
        tools = get_tool_definitions() if config.web_enabled else None

        # Response accumulation
        full_content = ""
        full_thinking = ""

        # Streaming loop with tool support
        max_iterations = 5
        iteration = 0

        while iteration < max_iterations and not self._cancelled:
            iteration += 1
            self._iteration = iteration

            # Stream response
            content_text, thinking_text, tool_calls = await self._stream_response(
                messages, tools, on_token, on_status
            )

            full_content += content_text
            full_thinking += thinking_text

            # If no tool calls, we're done
            if not tool_calls:
                break

            # Add assistant message with tool calls BEFORE executing tools,
            # so the session order is correct: assistant(tool_calls) → tool(results)
            assistant_tool_calls = self._normalize_tool_calls(tool_calls)
            self.session.add_assistant_message(content_text, tool_calls=assistant_tool_calls)
            await self._execute_tools(assistant_tool_calls, on_tool)

            # Update messages for next iteration
            messages = self.session.get_messages_for_api()

        # Finalize
        self.status.stop_generating()
        self.status.stop_thinking()
        self.status.finalize()

        # Add final assistant message
        if full_content:
            self.session.add_assistant_message(full_content)

        return {
            "success": bool(full_content) and not self._cancelled,
            "content": full_content,
            "thinking": full_thinking,
            "cancelled": self._cancelled,
            "error": "" if full_content or self._cancelled else "Model returned an empty response",
            "searches": self.status.search_count,
            "sources": self.status.source_count,
            "tools": self.status.tool_count,
            "tokens": self.status.token_count,
            "context_pct": self.status.context_percentage,
        }