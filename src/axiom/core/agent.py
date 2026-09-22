"""The AXIOM agent loop.

    USER → CONTEXT → MODEL → THINKING → DECISION
        → (TOOL / SEARCH) → TOOL RESULT → MODEL → FINAL ANSWER

Everything emitted here is driven by real backend activity: statuses are
transitions of :class:`~axiom.core.state_machine.GenerationStateMachine`,
reasoning appears only when the model actually sends it, and search results
only when a real search provider returned them.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from axiom.core.config import Config
from axiom.core.events import (
    ChatEvent,
    ContentChunk,
    ReasoningChunk,
    SearchResultEvent,
    SourceItem,
    StatusChange,
    ToolCallEvent,
    ToolResultEvent,
)
from axiom.core.models import ModelInfo
from axiom.core.ollama import OllamaClient, ToolCallRequest
from axiom.core.state import GenerationState
from axiom.core.state_machine import GenerationStateMachine
from axiom.core.tools.filesystem import WORKSPACE_TOOLS
from axiom.core.tools.git_tools import GIT_TOOLS
from axiom.core.tools.project_tools import PROJECT_TOOLS
from axiom.core.tools.registry import ToolRegistry
from axiom.core.tools.web_search import (
    FETCH_URL_TOOL,
    WEB_SEARCH_TOOL,
    WebSearchTool,
)

#: Hard limit on tool rounds — the agent must never loop forever.
MAX_TOOL_ROUNDS = 3

#: Tools the agent advertises to the model. ``fetch_url`` matters most when the
#: user pastes a link: the model must read the page instead of guessing.
OFFERED_TOOLS = (WEB_SEARCH_TOOL, FETCH_URL_TOOL)

#: Links the user pasted are read automatically — local models do not reliably
#: call tools on their own, so the agent must not depend on that.
MAX_AUTO_FETCH = 2

#: Characters of a fetched page handed to the model as context.
MAX_PAGE_CHARS = 6000

DEFAULT_SYSTEM_PROMPT = (
    "You are AXIOM, a precise local AI assistant running on the user's machine "
    "through Ollama. Answer directly and accurately. Use markdown when it helps. "
    "Never invent facts; if you are unsure, say so.\n\n"
    "You have real tools:\n"
    "- web_search(query) — search the public web; use it whenever the answer "
    "may depend on current or factual online information.\n"
    "- fetch_url(url) — read a web page; ALWAYS use it when the user gives a "
    "link, so you answer from the actual page content, not from memory.\n"
    "Do not say you cannot browse the web — you can, through these tools.\n\n"
    "You also have real workspace tools operating inside the user's project:\n"
    "- list_files(path) — list a directory to explore the project.\n"
    "- read_file(path) — read a file; ALWAYS read a file before editing it.\n"
    "- write_file(path, content) — create a new file or rewrite one entirely.\n"
    "- edit_file(path, old_text, new_text) — replace an exact unique snippet.\n"
    "- search_text(pattern) / search_files(glob) — find code by content/name.\n"
    "- create_directory(path), copy/move/delete (delete asks the user first).\n"
    "- run_command(command) — run tests/builds in the workspace (safe ones "
    "run at once, others ask the user first).\n"
    "- inspect_project() — describe the current project.\n"
    "- git_status/git_diff/git_log/git_branch — read-only git inspection.\n"
    "When the user asks about their project, do not guess: list and read the "
    "actual files. When asked to change code, read first, then edit or write. "
    "All paths are relative to the workspace root."
)

WORKSPACE_PROMPT_ADDON = (
    "\nWorkspace tools are enabled for this conversation. For project questions "
    "use list_files/read_file instead of guessing; for changes use edit_file "
    "with a unique exact snippet, or write_file for new files."
)


def workspace_context_block(root: str | None) -> str:
    """Short factual block about the current workspace (no full project dump).

    Keeps the model grounded in the real directory: path, project kind, git
    branch and the top-level layout. Never sends file contents — the agent
    must read what it needs via tools (spec §4: Project Index → AI Context).
    """
    if not root:
        return ""
    try:
        from pathlib import Path as _Path

        from axiom.core.workspace import detect_project as _detect

        info = _detect(_Path(root))
        lines = [
            f"Current workspace: {info.path}",
            f"Project: {info.name} ({info.kind})",
        ]
        if info.git:
            lines.append(f"Git: yes{(' — branch ' + info.branch) if info.branch else ''}")
        else:
            lines.append("Git: no repository")
        if info.entries:
            lines.append("Top-level: " + ", ".join(info.entries[:24]))
        return "\n".join(lines)
    except Exception:
        return f"Current workspace: {root}"

SEARCH_SYSTEM_PROMPT = (
    "You are AXIOM. The web search results below were fetched in real time from "
    "the public web. Base your answer on them, cite the sources you used as "
    "[number] where relevant, and state clearly when the sources do not answer "
    "the question."
)

PAGE_SYSTEM_PROMPT = (
    "You are AXIOM. The user gave a link and the pages below were read in real "
    "time from the live web — this is the actual page content, not your memory. "
    "Answer strictly from it, quote concrete details, and say plainly if the "
    "page does not contain what was asked. Never claim you cannot open links."
)


@dataclass
class PassResult:
    """Accumulated output of one model pass."""

    content: str = ""
    thinking: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    #: Real time-to-first-token of this pass (measured, not estimated).
    ttft_ms: int | None = None


class Agent:
    """Runs one generation cycle and yields structured events."""

    def __init__(
        self,
        client: OllamaClient,
        *,
        config: Config,
        registry: ToolRegistry,
        machine: GenerationStateMachine,
        web_tool: WebSearchTool | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._registry = registry
        self._machine = machine
        self._web_tool = web_tool
        self._max_rounds = MAX_TOOL_ROUNDS + (3 if config.workspace_tools_enabled else 0)
        self.last_sources: list[SourceItem] = []
        self.last_content = ""
        self.last_thinking = ""
        self.last_metrics: dict = {}
        self.metrics: dict = {}
        #: Pages read because the user pasted their links, as (url, text).
        self._pasted_pages: list[tuple[str, str]] = []

    # ------------------------------------------------------------------ utils

    def _status(self, state: GenerationState, detail: str | None = None) -> StatusChange | None:
        """Emit a status only when the state machine allows the transition."""
        if not self._machine.can(state):
            return None
        self._machine.transition(state)
        return StatusChange(state=state, detail=detail)

    def _build_messages(self, history: list[dict], system: str) -> list[dict]:
        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        return messages

    def _think_param(self, model: ModelInfo, history: list[dict]) -> bool | str | None:
        """Resolve the real ``think`` request parameter for this request.

        Priority: explicit config value (bool or level string) → thinking_mode
        preset → per-request heuristic → model capability. Deterministic only:
        the level depends on the message history shape, never on an extra LLM
        classifier call (which would double the latency it tries to save).
        """
        explicit = self._config.think
        if explicit is not None:
            return explicit
        mode = getattr(self._config, "thinking_mode", "auto")
        level = {"fast": "low", "normal": "medium", "deep": "high"}.get(mode)
        if level is not None:
            return level
        if model.supports("thinking") is not True:
            return None
        # Heuristic: hard tasks deserve deeper reasoning than small talk.
        user_text = self._last_user_text(history)
        if not user_text:
            return "low"
        text = user_text.lower()
        if any(
            marker in text
            for marker in (
                "почему", "придумай", "реши", "напиши", "рефактор", "отлад",
                "debug", "why ", "explain", "design", "optimi", "architect",
            )
        ):
            return "high"
        if len(text) > 200:
            return "medium"
        return "low"

    def _tool_schemas(
        self, model: ModelInfo, user_text: str | None = None
    ) -> list[dict] | None:
        """Only offer tools the model supports AND this request plausibly needs.

        A smaller tool schema means fewer prompt tokens per round on a local
        model. Git tools are only advertised when the request mentions git;
        file tools only when it mentions files/code or the request is clearly
        about the project. Web tools stay always-on (cheap, two entries).
        """
        if not self._config.web_search_enabled and not self._config.workspace_tools_enabled:
            return None
        if model.supports("tools") is not True:
            return None
        allowed: set[str] = set(OFFERED_TOOLS)
        if self._config.workspace_tools_enabled:
            text = (user_text or "").lower()
            mentions_git = any(
                marker in text
                for marker in ("git", "коммит", "commit", "ветк", "branch", "diff", "лог", "log")
            )
            mentions_files = any(
                marker in text
                for marker in (
                    "файл", "функци", "код", "проект", "папк", "рефактор", "ошибк",
                    "file", "code", "project", "folder", "refactor", "bug", "implement",
                    "test", "тест", "script", "скрипт", "модул", "class", "класс",
                )
            )
            if mentions_git:
                allowed.update(GIT_TOOLS)
            if mentions_files or not text:
                allowed.update(WORKSPACE_TOOLS)
                allowed.update(PROJECT_TOOLS)
                if self._config.terminal_enabled and self._config.access_mode != "read_only":
                    allowed.add("run_command")
        schemas = [s for s in self._registry.schemas() if s["function"]["name"] in allowed]
        return schemas or None

    @staticmethod
    def _int_or_none(value) -> int | None:
        """Pass real ints through, map anything else to ``None``."""
        return value if isinstance(value, int) else None

    @staticmethod
    def _metrics(metrics: dict, started: float, ttft_ms: int | None = None) -> dict:
        """Normalise Ollama metrics into UI-friendly values."""
        eval_count = metrics.get("eval_count")
        eval_duration = metrics.get("eval_duration")
        per_second = None
        if isinstance(eval_count, int) and isinstance(eval_duration, int) and eval_duration > 0:
            per_second = round(eval_count / (eval_duration / 1_000_000_000), 1)
        load_duration = metrics.get("load_duration")
        return {
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "tokens_out": eval_count if isinstance(eval_count, int) else None,
            "tokens_in": Agent._int_or_none(metrics.get("prompt_eval_count")),
            "tokens_per_second": per_second,
            "ttft_ms": ttft_ms,
            "load_ms": (
                round(load_duration / 1_000_000)
                if isinstance(load_duration, int) and load_duration > 0
                else None
            ),
        }

    # ------------------------------------------------------------- model pass

    async def _stream_pass(
        self,
        messages: list[dict],
        model: ModelInfo,
        *,
        think: bool | str | None,
        tools: list[dict] | None,
        result: PassResult,
    ) -> AsyncIterator[ChatEvent]:
        """Stream one real model pass, emitting reasoning/content deltas."""
        stream_started = time.perf_counter()
        saw_thinking = False
        saw_content = False
        first_token_at: float | None = None
        options: dict = {}
        if self._config.temperature is not None:
            options["temperature"] = self._config.temperature
        num_ctx = getattr(self._config, "num_ctx", None)
        if isinstance(num_ctx, int):
            options["num_ctx"] = num_ctx
        num_predict = getattr(self._config, "num_predict", None)
        if isinstance(num_predict, int):
            options["num_predict"] = num_predict
        async for chunk in self._client.chat(
            model.name,
            messages,
            think=think,
            tools=tools,
            options=options or None,
            keep_alive=getattr(self._config, "keep_alive", None),
        ):
            if first_token_at is None and (chunk.thinking or chunk.content or chunk.tool_calls):
                first_token_at = time.perf_counter()
                result.ttft_ms = int((first_token_at - stream_started) * 1000)
            if chunk.thinking:
                if not saw_thinking:
                    saw_thinking = True
                    status = self._status(GenerationState.THINKING)
                    if status:
                        yield status
                result.thinking += chunk.thinking
                yield ReasoningChunk(text=chunk.thinking)
            if chunk.content:
                if not saw_content:
                    saw_content = True
                    status = self._status(GenerationState.RECEIVING)
                    if status:
                        yield status
                result.content += chunk.content
                yield ContentChunk(text=chunk.content)
            if chunk.tool_calls:
                result.tool_calls.extend(chunk.tool_calls)
            if chunk.metrics:
                result.metrics = chunk.metrics
            if chunk.done:
                break

    async def _execute_tool(
        self, call: ToolCallRequest
    ) -> AsyncIterator[ChatEvent]:
        """Execute a model-requested tool and report the real outcome."""
        if call.name == WEB_SEARCH_TOOL:
            # The UI shows this detail to the user — it must be the real
            # query, not the tool name.
            detail = str(call.arguments.get("query") or call.name)
        elif call.name == FETCH_URL_TOOL:
            detail = str(call.arguments.get("url") or call.name)
        elif call.name == "run_command":
            detail = str(call.arguments.get("command") or call.name)
        elif call.name in ("read_file", "write_file", "edit_file", "delete_file"):
            detail = str(call.arguments.get("path") or call.name)
        elif call.name == "list_files":
            detail = str(call.arguments.get("path") or ".")
        elif call.name in ("search_text", "search_files"):
            detail = str(call.arguments.get("pattern") or call.arguments.get("glob") or call.name)
        else:
            detail = call.name
        status = self._status(
            GenerationState.SEARCHING
            if call.name == WEB_SEARCH_TOOL
            else GenerationState.TOOL_CALL,
            detail=detail,
        )
        if status:
            yield status
        yield ToolCallEvent(name=call.name, arguments=call.arguments)
        result = await self._registry.execute(call.name, call.arguments)
        yield ToolResultEvent(
            name=result.name,
            ok=result.ok,
            content=result.content if result.ok else "",
            error=result.error,
            duration_ms=result.duration_ms,
        )
        if call.name == WEB_SEARCH_TOOL and result.ok:
            query = str(call.arguments.get("query") or "")
            async for event in self._read_sources(query):
                yield event

    async def _read_sources(self, query: str) -> AsyncIterator[ChatEvent]:
        """Read the top sources of a real search — no simulation."""
        if self._web_tool is None:
            return
        sources = list(self._web_tool.last_sources)
        self.last_sources = [
            SourceItem(index=i, title=s.title, url=s.url, snippet=s.snippet)
            for i, s in enumerate(sources, start=1)
        ]
        if self.last_sources:
            yield SearchResultEvent(query=query, sources=self.last_sources)
        read_count = min(self._config.search_read_sources, len(sources))
        for source in sources[:read_count]:
            status = self._status(GenerationState.TOOL_CALL, detail="read_source")
            if status:
                yield status
            result = await self._registry.execute("fetch_url", {"url": source.url})
            yield ToolResultEvent(
                name="fetch_url",
                ok=result.ok,
                content=result.content[:1500] if result.ok else "",
                error=result.error,
                duration_ms=result.duration_ms,
            )

    #: Matches http(s) links a user may paste into a message.
    _URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+")

    @classmethod
    def _urls_in_text(cls, text: str) -> list[str]:
        """Links found in a message, de-duplicated, order preserved."""
        found: list[str] = []
        for raw in cls._URL_RE.findall(text or ""):
            url = raw.rstrip(".,;:!?")
            if url and url not in found:
                found.append(url)
        return found

    async def _read_pasted_links(self, history: list[dict]) -> AsyncIterator[ChatEvent]:
        """Read the pages a user linked, so answers come from the real content."""
        self._pasted_pages = []
        if self._web_tool is None or not self._config.web_search_enabled:
            return
        urls = self._urls_in_text(self._last_user_text(history))[:MAX_AUTO_FETCH]
        for url in urls:
            page = ""
            async for event in self._execute_tool(
                ToolCallRequest(name=FETCH_URL_TOOL, arguments={"url": url})
            ):
                if (
                    isinstance(event, ToolResultEvent)
                    and event.name == FETCH_URL_TOOL
                    and event.ok
                ):
                    page = event.content
                yield event
            if page:
                self._pasted_pages.append((url, page))
        if self._pasted_pages:
            self.last_sources = [
                SourceItem(
                    index=index,
                    title=url,
                    url=url,
                    snippet=" ".join(text.split())[:200],
                )
                for index, (url, text) in enumerate(self._pasted_pages, start=1)
            ]
            yield SearchResultEvent(query=urls[0], sources=self.last_sources)

    # ------------------------------------------------------------- agent loop

    async def run(
        self,
        history: list[dict],
        model: ModelInfo,
        *,
        force_search: bool = False,
        search_query: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """Run a full generation cycle, yielding every real step as an event."""
        started = time.perf_counter()
        self.last_sources = []
        self.last_content = ""
        self.last_thinking = ""
        self.last_metrics: dict = {}
        self._pasted_pages = []
        last_ttft: int | None = None

        system = self._config.system_prompt or DEFAULT_SYSTEM_PROMPT
        if self._config.workspace_tools_enabled and self._config.system_prompt is None:
            system += WORKSPACE_PROMPT_ADDON
        # §4: every request carries the real workspace path (path + kind +
        # top-level layout, never the whole project). After a project switch
        # this block points at the NEW folder, so the model works with it.
        if self._config.workspace_tools_enabled:
            block = workspace_context_block(self._config.workspace_root)
            if block:
                system = f"{system}\n\n{block}"
        if force_search:
            if not self._config.web_search_enabled or self._web_tool is None:
                from axiom.core.events import ErrorEvent

                yield ErrorEvent(
                    message="Web Search unavailable",
                    kind="search_unavailable",
                    hint="Enable web search in settings to use it.",
                )
            else:
                query = (search_query or "").strip() or self._last_user_text(history)
                search_block = ""
                search_failed = False
                async for event in self._execute_tool(
                    ToolCallRequest(name=WEB_SEARCH_TOOL, arguments={"query": query})
                ):
                    if isinstance(event, ToolResultEvent) and event.name == WEB_SEARCH_TOOL:
                        if event.ok:
                            search_block = event.content
                        else:
                            search_failed = True
                    yield event
                if search_block:
                    # Keep the configured system prompt and append the search
                    # context — a user's custom prompt must survive (same
                    # behaviour as the pasted-links branch below).
                    system = f"{system}\n\n{SEARCH_SYSTEM_PROMPT}\n\nSearch results:\n{search_block}"
                elif search_failed:
                    system = (
                        f"{DEFAULT_SYSTEM_PROMPT}\n\nLive web search was attempted but failed. "
                        "Answer from your own knowledge and state clearly that live sources "
                        "were unavailable."
                    )
        elif self._config.web_search_enabled and self._web_tool is not None:
            # A pasted link must be read for real. Small local models often skip
            # tools entirely, so the agent fetches the page instead of waiting.
            async for event in self._read_pasted_links(history):
                yield event
            pages = self._pasted_pages
            if pages:
                # Keep the configured system prompt and append the real page
                # content — a user's custom prompt must survive.
                page_block = "\n\n".join(
                    f"Page {index} — {url}\n{text[:MAX_PAGE_CHARS]}"
                    for index, (url, text) in enumerate(pages, start=1)
                )
                system = f"{system}\n\n{PAGE_SYSTEM_PROMPT}\n\nLive pages:\n{page_block}"

        messages = self._build_messages(history, system)
        think = self._think_param(model, history)
        user_text = self._last_user_text(history)
        rounds = 0
        while True:
            tools = self._tool_schemas(model, user_text)
            status = self._status(GenerationState.CONNECTING, detail=model.name)
            if status:
                yield status

            result = PassResult()
            async for event in self._stream_pass(
                messages, model, think=think, tools=tools, result=result
            ):
                yield event
            self.last_content += result.content
            self.last_thinking += result.thinking
            if result.metrics:
                self.last_metrics = result.metrics
            last_ttft = result.ttft_ms if result.ttft_ms is not None else last_ttft

            if not result.tool_calls:
                break
            if rounds >= self._max_rounds:
                break
            rounds += 1

            if result.content.strip():
                messages.append({"role": "assistant", "content": result.content})
            for call in result.tool_calls:
                tool_block = ""
                async for event in self._execute_tool(call):
                    if isinstance(event, ToolResultEvent) and event.ok:
                        tool_block = event.content
                    yield event
                if tool_block:
                    messages.append(
                        {
                            "role": "system",
                            "content": f"Tool result ({call.name}):\n{tool_block}",
                        }
                    )

        self.metrics = self._metrics(self.last_metrics, started, ttft_ms=last_ttft)

    @staticmethod
    def _last_user_text(history: list[dict]) -> str:
        for message in reversed(history):
            if message.get("role") == "user" and message.get("content"):
                return str(message["content"])
        return ""
