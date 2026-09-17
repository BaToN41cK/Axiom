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
from axiom.core.search.multi import MultiSearchProvider
from axiom.core.search.provider import SearchProvider
from axiom.core.state import GenerationState
from axiom.core.state_machine import GenerationStateMachine
from axiom.core.tools.registry import ToolRegistry
from axiom.core.tools.web_search import WebSearchTool

#: How many previous messages are sent back to the model.
CONTEXT_MESSAGES = 40


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
        self.history_store = history_store if history_store is not None else HistoryStore()
        self.provider = provider or MultiSearchProvider()
        self.web_tool = WebSearchTool(self.provider, max_sources=self.config.search_max_sources)
        self.tools = ToolRegistry()
        self.web_tool.register(self.tools)
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
        self.conversation.messages.append(
            Message(
                role="user",
                content=text,
                created_at=time.time(),
                images=[img for img in (images or []) if img],
            )
        )
        self.conversation.derive_title()

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
