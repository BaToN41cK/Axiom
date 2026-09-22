"""ChatSession — the public entry point of the AXIOM core.

Frontends interact with the engine exclusively through this class:

* :meth:`ChatSession.startup` — real Ollama/model probing for the splash screen.
* :meth:`ChatSession.send` — returns an ``AsyncIterator[ChatEvent]``.
* :meth:`ChatSession.cancel` — stop the in-flight generation.
* :meth:`ChatSession.switch_model`, :meth:`ChatSession.new_conversation`, ...

No UI framework is imported anywhere in this module.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from axiom.core.agent import Agent
from axiom.core.config import Config
from axiom.core.errors import (
    AxiomError,
)
from axiom.core.events import (
    ChatEvent,
    ContentChunk,
    Done,
    ErrorEvent,
    Message,
    ReasoningChunk,
    StatusChange,
)
from axiom.core.history import Conversation, HistoryStore
from axiom.core.models import ModelInfo, ModelRegistry
from axiom.core.ollama import OllamaClient
from axiom.core.profiles import ProfileManager
from axiom.core.search.multi import MultiSearchProvider
from axiom.core.search.provider import SearchProvider
from axiom.core.state import GenerationState
from axiom.core.state_machine import GenerationStateMachine
from axiom.core.tools.base import ToolPermission
from axiom.core.tools.filesystem import WORKSPACE_TOOLS, WorkspaceTools
from axiom.core.tools.git_tools import (
    GIT_BRANCH_TOOL,
    GIT_DIFF_TOOL,
    GIT_LOG_TOOL,
    GIT_STATUS_TOOL,
    GitTools,
)
from axiom.core.tools.project_tools import INSPECT_PROJECT_TOOL, ProjectTools
from axiom.core.tools.registry import ToolRegistry
from axiom.core.tools.terminal import RUN_COMMAND_TOOL, TerminalTool, classify_command
from axiom.core.tools.web_search import WebSearchTool
from axiom.core.workspace import ProjectInfo, WorkspaceManager, detect_project

#: How many previous messages are sent back to the model.
CONTEXT_MESSAGES = 40

#: Every tool that touches the workspace filesystem. Global Chat (no project)
#: drops exactly these from the registry; :meth:`set_workspace` puts them back.
WORKSPACE_TOOL_NAMES: frozenset[str] = frozenset(WORKSPACE_TOOLS) | {
    GIT_STATUS_TOOL,
    GIT_DIFF_TOOL,
    GIT_LOG_TOOL,
    GIT_BRANCH_TOOL,
    INSPECT_PROJECT_TOOL,
    RUN_COMMAND_TOOL,
}


@dataclass
class StartupReport:
    """Result of the real startup probe (drives the splash screen)."""

    ollama_available: bool = False
    version: str | None = None
    models: list[ModelInfo] = field(default_factory=list)
    selected: ModelInfo | None = None
    error: str | None = None
    hint: str | None = None


class ChatSession:
    """Owns the conversation, the agent loop and the local persistence."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        client: OllamaClient | None = None,
        registry: ModelRegistry | None = None,
        history_store: HistoryStore | None = None,
        provider: SearchProvider | None = None,
    ) -> None:
        self.config = config or Config.load()
        self.client = client or OllamaClient(self.config.ollama_url)
        self.registry = registry or ModelRegistry(self.client)
        self.history_store = history_store if history_store is not None else HistoryStore(
            limit=self.config.history_limit if self.config.save_history else None
        )
        self.provider = provider or MultiSearchProvider(timeout=self.config.search_timeout)
        self.web_tool = WebSearchTool(self.provider, max_sources=self.config.search_max_sources)
        self.tools = ToolRegistry()
        self.web_tool.register(self.tools)
        # §8 Tool Layer: file tools + terminal tools + project tools +
        # git tools + web tools — all behind the permission system (§9-§12).
        # Workspace tools always exist: an explicit ``workspace_root`` wins,
        # otherwise they are rooted at the launch directory
        # (``default_workspace_root`` — the Tauri shell exports
        # ``AXIOM_WORKSPACE``; CLI/TUI fall back to the current directory).
        # A real project switch happens via :meth:`set_workspace`.
        self.workspace_tools: WorkspaceTools | None = None
        self.git_tools = None
        self.project_tools = None
        if self.config.workspace_tools_enabled:
            root = (
                Path(self.config.workspace_root).expanduser()
                if self.config.workspace_root
                else None  # WorkspaceTools resolves None -> default_workspace_root()
            )
            self.workspace_tools = WorkspaceTools(root, access_mode=self.config.access_mode)
            self.workspace_tools.register(self.tools)
            from axiom.core.tools.git_tools import GitTools
            from axiom.core.tools.project_tools import ProjectTools

            self.git_tools = GitTools(root)
            self.git_tools.register(self.tools)
            self.project_tools = ProjectTools(root)
            self.project_tools.register(self.tools)
        self.terminal: TerminalTool | None = None
        if self.config.workspace_tools_enabled and self.config.terminal_enabled:
            self.terminal = TerminalTool(
                root=Path(self.config.workspace_root).expanduser()
                if self.config.workspace_root
                else None,
                enabled=self.config.access_mode != "read_only",
            )
            self.terminal.register(self.tools)
        self.workspaces = WorkspaceManager()
        if self.config.workspace_root:
            self.workspaces.remember(Path(self.config.workspace_root))
        self.machine = GenerationStateMachine()
        self.agent = Agent(
            self.client,
            config=self.config,
            registry=self.tools,
            machine=self.machine,
            web_tool=self.web_tool,
        )
        self.conversation = Conversation(model=self.config.model)
        self.active_model: ModelInfo | None = None
        self.last_metrics: dict = {}
        self._task: asyncio.Task | None = None
        #: Profile manager — system prompt profiles
        self.profiles = ProfileManager()

    # ------------------------------------------------------------- lifecycle

    @property
    def busy(self) -> bool:
        """True while a generation is really in flight."""
        return self._task is not None and not self._task.done()

    @property
    def model(self) -> ModelInfo | None:
        return self.active_model

    @property
    def state(self) -> GenerationState:
        return self.machine.state

    async def startup(self) -> StartupReport:
        """Probe Ollama and discover models — every step is real."""
        try:
            if not await self.client.is_available():
                return StartupReport(
                    ollama_available=False,
                    error="Ollama is not reachable.",
                    hint=f"Start Ollama and make sure it listens on {self.client.base_url}",
                )
            version = await self.client.version()
            models = await self.registry.refresh()
            if not models:
                return StartupReport(
                    ollama_available=True,
                    version=version,
                    error="No models are installed.",
                    hint="Install one with: ollama pull qwen3:8b",
                )
            selected = self.registry.resolve(self.config.model)
            if selected is not None:
                self.active_model = selected
                ModelRegistry.persist_selection(self.config, selected.name)
                self.conversation.model = selected.name
            return StartupReport(
                ollama_available=True,
                version=version,
                models=models,
                selected=selected,
            )
        except AxiomError as exc:
            return StartupReport(ollama_available=False, error=str(exc), hint=exc.hint)

    async def refresh_models(self) -> list[ModelInfo]:
        return await self.registry.refresh()

    async def model_detail(self, name: str | None = None) -> ModelInfo | None:
        """Full descriptor (real context window) of *name* or the active model."""
        target = name or (self.active_model.name if self.active_model else None)
        if not target:
            return None
        detail = await self.registry.detail(target)
        if detail is not None and self.active_model is not None and detail.name == self.active_model.name:
            self.active_model = detail
        return detail

    def tools_info(self) -> list[dict[str, Any]]:
        """Agent tools as the backend really declares them (name/description/permission)."""
        return [
            {
                "name": definition.name,
                "description": definition.description,
                "permission": definition.permission.value,
            }
            for definition in self.tools.definitions()
        ]

    async def reconnect(self, ollama_url: str | None = None) -> StartupReport:
        """Apply a new Ollama URL (if given) and probe again."""
        if ollama_url and ollama_url.strip() and ollama_url.strip() != self.client.base_url:
            self.config.ollama_url = ollama_url.strip()
            self.config.save()
            self.client = OllamaClient(self.config.ollama_url)
            self.registry = ModelRegistry(self.client)
            self.agent = Agent(
                self.client,
                config=self.config,
                registry=self.tools,
                machine=self.machine,
                web_tool=self.web_tool,
            )
        return await self.startup()

    # ---------------------------------------------------------------- models

    async def switch_model(self, name: str) -> ModelInfo:
        """Switch the active model (persisted). Raises if it does not exist."""
        model = self.registry.get(name)
        if model is None:
            await self.registry.refresh()
            model = self.registry.get(name)
        if model is None:
            from axiom.core.errors import ModelNotFoundError

            raise ModelNotFoundError(f"Model '{name}' is not available in Ollama.")
        self.active_model = model
        self.conversation.model = model.name
        ModelRegistry.persist_selection(self.config, model.name)
        self._save_conversation()
        return model

    # ----------------------------------------------------------- conversations

    def new_conversation(self) -> Conversation:
        """Start a fresh conversation (the current one is already persisted)."""
        self._save_conversation()
        self.conversation = Conversation(model=self.active_model.name if self.active_model else None)
        return self.conversation

    def load_conversation(self, conversation_id: str) -> Conversation | None:
        self._save_conversation()
        loaded = self.history_store.load(conversation_id)
        if loaded is None:
            return None
        self.conversation = loaded
        return loaded

    def history(self) -> list[Conversation]:
        return self.history_store.list()

    def delete_conversation(self, conversation_id: str) -> bool:
        if conversation_id == self.conversation.id:
            self.conversation = Conversation(
                model=self.active_model.name if self.active_model else None
            )
        return self.history_store.delete(conversation_id)

    def rename_conversation(self, conversation_id: str, title: str) -> bool:
        """Rename a stored conversation; the in-memory one is updated too."""
        renamed = self.history_store.rename(conversation_id, title)
        if renamed and conversation_id == self.conversation.id:
            self.conversation.title = " ".join(title.split())[:80]
        return renamed

    # -------------------------------------------------------------- workspace

    @property
    def workspace_root(self) -> Path | None:
        # Global Chat turns workspace tooling off; reporting a root then would
        # keep the GUI (explorer / git / terminal) bound to a closed project.
        if self.workspace_tools is None or not self.config.workspace_tools_enabled:
            return None
        return self.workspace_tools.root

    def workspace_info(self) -> ProjectInfo | None:
        root = self.workspace_root
        return detect_project(root) if root and root.exists() else None

    def recent_workspaces(self) -> list[ProjectInfo]:
        return self.workspaces.recent()

    def pinned_workspaces(self) -> list[ProjectInfo]:
        return self.workspaces.pinned_projects()

    def is_workspace_pinned(self, path: str) -> bool:
        return self.workspaces.is_pinned(path)

    def pin_workspace(self, path: str) -> bool:
        return self.workspaces.pin(path)

    def unpin_workspace(self, path: str) -> bool:
        return self.workspaces.unpin(path)

    def search_projects(self, query: str) -> list[ProjectInfo]:
        return self.workspaces.search_projects(query)

    def create_project(self, path: str) -> ProjectInfo:
        """Create a new project directory and remember it."""
        return self.workspaces.create_project(Path(path).expanduser().resolve())

    def remove_workspace(self, path: str) -> bool:
        return self.workspaces.remove(path)

    def set_workspace(self, path: str) -> ProjectInfo:
        """Switch the whole session to a real directory (AI + terminal + explorer)."""
        target = Path(path).expanduser().resolve()
        if not target.is_dir():
            from axiom.core.errors import AxiomError

            raise AxiomError(f"Not a directory: {target}")
        # §13/§22: keep the previous conversation on disk, then move this
        # session to the new project's own history dir — histories never mix.
        self._save_conversation()
        self.history_store.use_workspace(target)
        self.conversation = Conversation(model=self.active_model.name if self.active_model else None)
        self._save_conversation()
        self.config.workspace_root = str(target)
        # Leaving Global Chat re-enables workspace tooling for the new project.
        self.config.workspace_tools_enabled = True
        self.config.save()
        if self.workspace_tools is not None:
            self.workspace_tools.set_root(target)
            # Re-register: clear_workspace() dropped these names from the registry.
            self.workspace_tools.register(self.tools)
        else:
            # Tools were never created (config disabled them earlier) — build now.
            self.workspace_tools = WorkspaceTools(target, access_mode=self.config.access_mode)
            self.workspace_tools.register(self.tools)
            self.git_tools = GitTools(target)
            self.git_tools.register(self.tools)
            self.project_tools = ProjectTools(target)
            self.project_tools.register(self.tools)
        if self.git_tools is not None:
            self.git_tools.set_root(target)
            self.git_tools.register(self.tools)
        if self.project_tools is not None:
            self.project_tools.set_root(target)
            self.project_tools.register(self.tools)
        if self.terminal is not None:
            self.terminal.set_root(target)
            self.terminal.enabled = self.config.access_mode != "read_only"
            self.terminal.register(self.tools)
        elif self.config.terminal_enabled and self.config.access_mode != "read_only":
            self.terminal = TerminalTool(root=target, enabled=True)
            self.terminal.register(self.tools)
        self.workspaces.remember(target)
        return detect_project(target)

    def clear_workspace(self) -> None:
        """Leave project mode: Global Chat with no filesystem/terminal tools.

        The conversation stays on disk (project history dir), the store points
        back at the global history dir, and every workspace tool is removed
        from the registry so the model chats over Ollama only.
        """
        self._save_conversation()
        self.history_store.use_workspace(None)
        self.conversation = Conversation(model=self.active_model.name if self.active_model else None)
        self._save_conversation()
        self.config.workspace_root = None
        # Persist Global Chat across restarts: no workspace tools on boot.
        self.config.workspace_tools_enabled = False
        self.config.save()
        for name in WORKSPACE_TOOL_NAMES:
            self.tools.unregister(name)
        if self.terminal is not None:
            self.terminal.enabled = False

    async def run_terminal(self, command: str, confirmed: bool = False) -> dict:
        """Run a real shell command in the workspace (GUI terminal panel).

        Safe commands run immediately; anything else returns ``permission:
        "ask"`` so the GUI can confirm with the user first.
        """
        if self.terminal is None:
            return {"ok": False, "error": "Terminal access is disabled", "permission": "blocked"}
        if classify_command(command) == ToolPermission.ALWAYS or confirmed:
            result = await self.terminal._run(command)
            return {
                "ok": result.ok,
                "content": result.content,
                "error": result.error,
                "exit_code": (result.data or {}).get("exit_code"),
                "cwd": (result.data or {}).get("cwd"),
                "permission": "granted",
            }
        return {"ok": False, "permission": "ask", "command": command}

    def _save_conversation(self) -> None:
        if not self.config.save_history:
            return
        if not self.conversation.messages:
            return
        try:
            self.history_store.save(self.conversation)
        except OSError:
            # persistence must never break a chat session
            pass

    # ------------------------------------------------------------ generation

    def cancel(self) -> bool:
        """Cancel the in-flight generation. Returns True if something was stopped."""
        if self.busy and self._task is not None:
            self._task.cancel()
            return True
        return False

    async def send(
        self,
        text: str,
        *,
        force_search: bool = False,
        search_query: str | None = None,
        images: list[str] | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """Send a user message and stream the resulting events.

        Cancellation is supported through :meth:`cancel`; partial output is
        preserved and reported with a ``CANCELLED`` terminal event.
        """
        text = text.strip()
        images = [img for img in (images or []) if img]
        if not text and not images:
            return
        async for event in self._run_turn(
            text,
            force_search=force_search,
            search_query=search_query,
            images=images,
            record_user=True,
        ):
            yield event

    async def regenerate(self, *, force_search: bool = False) -> AsyncIterator[ChatEvent]:
        """Re-run the last turn: the stored assistant answer is dropped first.

        The backend really rewrites history here (no client-side illusion):
        the previous assistant message is removed from the conversation before
        the agent runs again on the same context.
        """
        if self.busy:
            yield ErrorEvent(
                message="A generation is already running.",
                kind="busy",
                hint="Stop it before regenerating.",
            )
            return
        last_user = next(
            (m.content for m in reversed(self.conversation.messages) if m.role == "user"),
            "",
        )
        if not last_user:
            yield ErrorEvent(
                message="There is nothing to regenerate.",
                kind="empty_history",
                hint="Send a message first.",
            )
            yield Done(state=GenerationState.ERROR)
            return
        if self.conversation.messages and self.conversation.messages[-1].role == "assistant":
            self.conversation.messages.pop()
        self._save_conversation()
        async for event in self._run_turn(
            last_user,
            force_search=force_search,
            search_query=None,
            images=[],
            record_user=False,
        ):
            yield event

    async def edit_last_user(self, text: str, *, force_search: bool = False) -> AsyncIterator[ChatEvent]:
        """Replace the last user turn and everything after it, then re-run.

        Editing a sent message is a real history rewrite: the backend drops the
        old user message (and the answer that followed it) before generating
        again — no duplicated turns pile up in the stored conversation.
        """
        text = text.strip()
        if not text:
            yield ErrorEvent(message="The message cannot be empty.", kind="empty_message")
            return
        if self.busy:
            yield ErrorEvent(
                message="A generation is already running.",
                kind="busy",
                hint="Stop it before editing.",
            )
            return
        index = next(
            (i for i in range(len(self.conversation.messages) - 1, -1, -1)
             if self.conversation.messages[i].role == "user"),
            None,
        )
        if index is None:
            yield ErrorEvent(
                message="There is no user message to edit.",
                kind="empty_history",
            )
            yield Done(state=GenerationState.ERROR)
            return
        del self.conversation.messages[index:]
        async for event in self._run_turn(
            text,
            force_search=force_search,
            search_query=None,
            images=[],
            record_user=True,
        ):
            yield event

    async def _run_turn(
        self,
        text: str,
        *,
        force_search: bool,
        search_query: str | None,
        images: list[str],
        record_user: bool,
    ) -> AsyncIterator[ChatEvent]:
        """Shared body of ``send`` / ``regenerate`` — one real generation cycle."""
        if self.busy:
            yield ErrorEvent(
                message="A generation is already running.",
                kind="busy",
                hint="Stop it before sending another message.",
            )
            return
        if self.active_model is None:
            report = await self.startup()
            if self.active_model is None:
                yield ErrorEvent(
                    message=report.error or "No model is available.",
                    kind="model_not_found",
                    hint=report.hint,
                )
                yield Done(state=GenerationState.ERROR)
                return

        if images and self.active_model is not None and self.active_model.supports("vision") is not True:
            yield ErrorEvent(
                message=(
                    f"The model '{self.active_model.name}' does not support images."
                ),
                kind="vision_unsupported",
                hint="Switch to a vision model (e.g. llava, llama3.2-vision, qwen2.5vl).",
            )
            yield Done(state=GenerationState.ERROR)
            return

        self.machine.reset()
        if record_user:
            self.conversation.messages.append(
                Message(
                    role="user",
                    content=text,
                    created_at=time.time(),
                    images=[img for img in (images or []) if img],
                )
            )
            self.conversation.derive_title()
            # Persist the user turn immediately: the chat appears in the
            # sidebar at once and survives a core crash mid-generation.
            self._save_conversation()
        elif images:
            # Regeneration keeps the original images of the recorded user turn.
            self.conversation.messages.append(
                Message(role="user", content=text, created_at=time.time(), images=list(images))
            )

        queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()
        self._task = asyncio.create_task(
            self._produce(text, queue, force_search=force_search, search_query=search_query)
        )
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
        self._task = None

    # --------------------------------------------------------------- internals

    def _context_messages(self) -> list[dict]:
        """Convert stored messages into the Ollama request format."""
        history: list[dict] = []
        for message in self.conversation.messages[-CONTEXT_MESSAGES:]:
            if message.role in ("user", "assistant") and (message.content or message.images):
                entry: dict[str, Any] = {"role": message.role, "content": message.content}
                if message.images:
                    # Ollama vision models expect base64 images per message.
                    entry["images"] = message.images
                history.append(entry)
        return history

    def _final_status(self, target: GenerationState) -> StatusChange | None:
        """Emit a terminal status if the state machine allows it."""
        if not self.machine.can(target):
            return None
        self.machine.transition(target)
        return StatusChange(state=target)

    def _final_status_to(self, queue: asyncio.Queue[ChatEvent | None], target: GenerationState) -> None:
        metrics = dict(getattr(self.agent, "metrics", {}) or {})
        status = self._final_status(target)
        if status:
            queue.put_nowait(status)
        queue.put_nowait(
            Done(
                state=target,
                duration_ms=metrics.get("duration_ms", 0),
                tokens_out=metrics.get("tokens_out"),
                tokens_in=metrics.get("tokens_in"),
                tokens_per_second=metrics.get("tokens_per_second"),
            )
        )

    @staticmethod
    def _empty_answer_event(thinking: str) -> ErrorEvent:
        """Empty-answer protection: never report a false ``Completed``."""
        if thinking:
            return ErrorEvent(
                message="The model returned reasoning but no final answer.",
                kind="empty_response",
                hint="Try rephrasing the request or switch to another model.",
            )
        return ErrorEvent(
            message="The model returned an empty response.",
            kind="empty_response",
            hint="Try again or switch to another model.",
        )

    def _record_turn(self, user_text: str, content: str, thinking: str) -> None:
        """Store the assistant turn (partial output is kept on cancellation)."""
        if content or thinking:
            self.conversation.messages.append(
                Message(
                    role="assistant",
                    content=content,
                    thinking=thinking or None,
                    created_at=time.time(),
                )
            )
        self._save_conversation()

    async def _produce(
        self,
        text: str,
        queue: asyncio.Queue[ChatEvent | None],
        *,
        force_search: bool,
        search_query: str | None,
    ) -> None:
        """Run the agent loop and push every real event into the queue."""
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        try:
            model = self.active_model
            if model is None:  # guarded by send(), kept for safety
                queue.put_nowait(ErrorEvent(message="No model is available.", kind="model_not_found"))
                self._final_status_to(queue, GenerationState.ERROR)
                return
            async for event in self.agent.run(
                self._context_messages(), model, force_search=force_search, search_query=search_query
            ):
                if isinstance(event, ContentChunk):
                    content_parts.append(event.text)
                elif isinstance(event, ReasoningChunk):
                    thinking_parts.append(event.text)
                queue.put_nowait(event)

            metrics = dict(self.agent.metrics)
            self.last_metrics = metrics
            content = "".join(content_parts).strip()
            thinking = "".join(thinking_parts).strip()
            if not content:
                queue.put_nowait(self._empty_answer_event(thinking))
                self._final_status_to(queue, GenerationState.ERROR)
                self._record_turn(text, "", thinking)
                return
            status = self._final_status(GenerationState.COMPLETED)
            if status:
                queue.put_nowait(status)
            queue.put_nowait(
                Done(
                    state=GenerationState.COMPLETED,
                    duration_ms=metrics.get("duration_ms", 0),
                    tokens_out=metrics.get("tokens_out"),
                    tokens_in=metrics.get("tokens_in"),
                    tokens_per_second=metrics.get("tokens_per_second"),
                )
            )
            self._record_turn(text, content, thinking)
        except asyncio.CancelledError:
            self._final_status_to(queue, GenerationState.CANCELLED)
            self._record_turn(text, "".join(content_parts).strip(), "".join(thinking_parts).strip())
            raise
        except AxiomError as exc:
            queue.put_nowait(ErrorEvent(message=str(exc), kind=exc.kind, hint=exc.hint))
            self._final_status_to(queue, GenerationState.ERROR)
        except Exception as exc:
            queue.put_nowait(
                ErrorEvent(
                    message=f"{type(exc).__name__}: {exc}",
                    kind="internal",
                    hint="This is an internal error. The session is still usable.",
                )
            )
            self._final_status_to(queue, GenerationState.ERROR)
        finally:
            queue.put_nowait(None)
