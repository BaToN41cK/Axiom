"""Config passthrough and vision tests for the real generation path."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from axiom.core.chat import ChatSession
from axiom.core.config import Config
from axiom.core.events import ErrorEvent, Message
from axiom.core.history import HistoryStore
from axiom.core.models import ModelInfo
from axiom.core.ollama import OllamaClient, StreamChunk
from axiom.core.search.multi import MultiSearchProvider


class FakeClient(OllamaClient):
    def __init__(self, chunks: list[StreamChunk] | None = None) -> None:
        super().__init__()
        self._chunks = chunks or [StreamChunk(content="ok"), StreamChunk(done=True)]
        self.chat_calls: list[dict[str, Any]] = []

    async def is_available(self) -> bool:
        return True

    async def version(self) -> str:
        return "0.0-test"

    async def list_models(self) -> list[dict[str, Any]]:
        return [{"name": "test-model:latest", "details": {}, "capabilities": []}]

    async def chat(  # type: ignore[override]
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        think: bool | str | None = None,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.chat_calls.append(
            {"model": model, "messages": messages, "think": think, "tools": tools, "options": options}
        )
        for chunk in self._chunks:
            yield chunk


def make_session(
    tmp_path: Path, *, config: Config | None = None, capabilities: list[str] | None = None
) -> tuple[ChatSession, FakeClient]:
    cfg = config or Config(model="test-model:latest")
    client = FakeClient()
    store = HistoryStore(directory=tmp_path / "history")
    session = ChatSession(config=cfg, client=client, history_store=store)
    session.active_model = ModelInfo(name="test-model:latest", capabilities=capabilities or [])
    return session, client


async def _collect(session: ChatSession, **kwargs: Any) -> list:
    return [event async for event in session.send("hi", **kwargs)]


# ---------------------------------------------------------------- defaults

def test_default_provider_is_multi_search(tmp_path: Path):
    session, _ = make_session(tmp_path)
    assert isinstance(session.provider, MultiSearchProvider)


# ------------------------------------------------------- temperature/system

async def test_temperature_reaches_ollama_options(tmp_path: Path):
    cfg = Config(model="test-model:latest", temperature=0.3)
    session, client = make_session(tmp_path, config=cfg)
    await _collect(session)
    assert client.chat_calls[0]["options"] == {"temperature": 0.3}


async def test_no_temperature_means_no_options(tmp_path: Path):
    session, client = make_session(tmp_path)  # temperature=None by default
    await _collect(session)
    assert client.chat_calls[0]["options"] is None


async def test_custom_system_prompt_is_used(tmp_path: Path):
    cfg = Config(model="test-model:latest", system_prompt="You are a pirate.")
    session, client = make_session(tmp_path, config=cfg)
    await _collect(session)
    first = client.chat_calls[0]["messages"][0]
    assert first["role"] == "system"
    assert first["content"] == "You are a pirate."


# ----------------------------------------------------------------- vision

async def test_images_on_non_vision_model_is_rejected(tmp_path: Path):
    session, client = make_session(tmp_path, capabilities=[])
    events = await _collect(session, images=["aGVsbG8="])
    assert any(
        isinstance(e, ErrorEvent) and e.kind == "vision_unsupported" for e in events
    )
    # nothing was sent to the model and nothing was recorded
    assert client.chat_calls == []
    assert session.conversation.messages == []


async def test_images_on_vision_model_reach_ollama(tmp_path: Path):
    session, client = make_session(tmp_path, capabilities=["vision"])
    await _collect(session, images=["aGVsbG8="])
    call = client.chat_calls[0]
    user = call["messages"][-1]
    assert user["role"] == "user"
    assert user["images"] == ["aGVsbG8="]
    # persisted in history too
    stored_user = session.conversation.messages[-2]
    assert isinstance(stored_user, Message)
    assert stored_user.images == ["aGVsbG8="]


async def test_send_without_images_unchanged(tmp_path: Path):
    session, client = make_session(tmp_path)
    await _collect(session)
    assert "images" not in client.chat_calls[0]["messages"][-1]
