"""Event flow tests for ChatSession.send() with a fake Ollama client."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from axiom.core.chat import ChatSession
from axiom.core.config import Config
from axiom.core.events import ContentChunk, Done, ErrorEvent, ReasoningChunk
from axiom.core.history import HistoryStore
from axiom.core.models import ModelInfo
from axiom.core.ollama import StreamChunk
from axiom.core.state import GenerationState


class FakeClient:
    """Minimal OllamaClient double driven by a scripted chunk list."""

    def __init__(
        self,
        chunks: list[StreamChunk] | None = None,
        *,
        base_url: str = "http://127.0.0.1:11434",
        block: asyncio.Event | None = None,
    ) -> None:
        self._chunks = chunks or []
        self._block = block
        self._base_url = base_url
        self.chat_calls: list[dict[str, Any]] = []

    @property
    def base_url(self) -> str:
        return self._base_url

    async def is_available(self) -> bool:
        return True

    async def version(self) -> str:
        return "0.0-test"

    async def list_models(self) -> list[dict[str, Any]]:
        return [{"name": "test-model:latest", "details": {}, "capabilities": []}]

    async def chat(self, model: str, messages: list[dict], **kwargs: Any):
        self.chat_calls.append({"model": model, "messages": messages, **kwargs})
        if self._block is not None:
            await self._block.wait()
        for chunk in self._chunks:
            yield chunk


def make_session(
    tmp_path: Path, chunks: list[StreamChunk] | None = None, **kwargs: Any
) -> ChatSession:
    cfg = Config(model="test-model:latest")
    store = HistoryStore(directory=tmp_path / "history")
    session = ChatSession(
        config=cfg, client=FakeClient(chunks, **kwargs), history_store=store
    )
    session.active_model = ModelInfo(name="test-model:latest", capabilities=[])
    return session


async def collect(session: ChatSession, text: str = "hello") -> list:
    return [event async for event in session.send(text)]


async def test_send_streams_reasoning_then_content_and_completes(tmp_path: Path):
    session = make_session(
        tmp_path,
        [
            StreamChunk(thinking="let me think"),
            StreamChunk(content="final answer"),
            StreamChunk(done=True, done_reason="stop"),
        ],
    )
    events = await collect(session)
    assert any(isinstance(e, ReasoningChunk) and "think" in e.text for e in events)
    assert any(isinstance(e, ContentChunk) and "final" in e.text for e in events)
    done = [e for e in events if isinstance(e, Done)]
    assert len(done) == 1
    assert done[0].state is GenerationState.COMPLETED
    # no false error alongside a good answer
    assert not [e for e in events if isinstance(e, ErrorEvent)]
    # reasoning stored separately from content, never merged
    stored = session.conversation.messages[-1]
    assert stored.content == "final answer"
    assert stored.thinking == "let me think"


async def test_thinking_and_content_not_mixed(tmp_path: Path):
    session = make_session(
        tmp_path,
        [StreamChunk(thinking="r1"), StreamChunk(content="c1"), StreamChunk(done=True)],
    )
    events = await collect(session)
    reasoning_text = "".join(e.text for e in events if isinstance(e, ReasoningChunk))
    content_text = "".join(e.text for e in events if isinstance(e, ContentChunk))
    assert reasoning_text == "r1"
    assert content_text == "c1"


async def test_empty_answer_is_error_not_completed(tmp_path: Path):
    session = make_session(tmp_path, [StreamChunk(done=True, done_reason="stop")])
    events = await collect(session)
    assert any(isinstance(e, ErrorEvent) and e.kind == "empty_response" for e in events)
    done = [e for e in events if isinstance(e, Done)]
    assert done and done[0].state is GenerationState.ERROR
    assert session.machine.state is GenerationState.ERROR


async def test_reasoning_without_content_is_still_empty_response(tmp_path: Path):
    session = make_session(tmp_path, [StreamChunk(thinking="only thoughts")])
    events = await collect(session)
    assert any(isinstance(e, ErrorEvent) and e.kind == "empty_response" for e in events)
    assert not [
        e
        for e in events
        if isinstance(e, Done) and e.state is GenerationState.COMPLETED
    ]


async def test_cancel_preserves_partial_output(tmp_path: Path):
    block = asyncio.Event()
    session = make_session(tmp_path, [StreamChunk(content="partial")], block=block)
    collected: list = []

    async def consume() -> None:
        async for event in session.send("long task"):
            collected.append(event)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    assert session.busy
    assert session.cancel() is True
    block.set()
    await task
    done = [e for e in collected if isinstance(e, Done)]
    assert done and done[0].state is GenerationState.CANCELLED
    assert session.machine.state is GenerationState.CANCELLED


async def test_second_send_while_busy_is_rejected(tmp_path: Path):
    block = asyncio.Event()
    session = make_session(tmp_path, [StreamChunk(content="x")], block=block)
    first = asyncio.create_task(collect(session, "first"))
    await asyncio.sleep(0.05)
    second = await collect(session, "second")
    assert any(isinstance(e, ErrorEvent) and e.kind == "busy" for e in second)
    block.set()
    await first


async def test_conversation_persisted_between_sends(tmp_path: Path):
    session = make_session(
        tmp_path, [StreamChunk(content="answer one"), StreamChunk(done=True)]
    )
    await collect(session, "question one")
    saved = HistoryStore(directory=tmp_path / "history").list()
    assert len(saved) == 1
    assert saved[0].messages[0].content == "question one"
    assert saved[0].messages[-1].content == "answer one"
