"""Pasted-link reading: AXIOM must fetch real pages even without tool support.

Regression target: reasoning models (e.g. ``deepseek-r1``) answer
"I cannot browse the web" and never emit ``tool_calls``, so the agent has to
read links the user provided on its own.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from axiom.core.agent import MAX_AUTO_FETCH
from axiom.core.chat import ChatSession
from axiom.core.config import Config
from axiom.core.events import SearchResultEvent, ToolCallEvent
from axiom.core.history import HistoryStore
from axiom.core.models import ModelInfo
from axiom.core.ollama import OllamaClient, StreamChunk
from axiom.core.search.provider import SearchProvider, SearchResult

PAGE_TEXT = "Курс №9: обучение по охране труда. Раздел 990 содержит требования."


class FakeProvider(SearchProvider):
    """Search backend that records what the agent really asked for."""

    name = "fake"

    def __init__(self) -> None:
        self.searched: list[str] = []
        self.fetched: list[str] = []

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        self.searched.append(query)
        return [SearchResult(title="Result", url="https://example.com/r", snippet="snip")]

    async def fetch(self, url: str, max_chars: int = 4000) -> str:
        self.fetched.append(url)
        return PAGE_TEXT


class FakeClient(OllamaClient):
    """Minimal client double that never emits tool calls, like deepseek-r1."""

    def __init__(self) -> None:
        super().__init__()
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
        think: bool | None = None,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.chat_calls.append({"model": model, "messages": messages, "tools": tools})
        yield StreamChunk(content="answer")
        yield StreamChunk(done=True)


def make_session(
    tmp_path: Path,
    *,
    capabilities: list[str] | None = None,
    workspace_tools: bool = False,
) -> tuple[ChatSession, FakeClient, FakeProvider]:
    client = FakeClient()
    provider = FakeProvider()
    session = ChatSession(
        config=Config(model="test-model:latest", workspace_tools_enabled=workspace_tools),
        client=client,
        provider=provider,
        history_store=HistoryStore(directory=tmp_path / "history"),
    )
    session.active_model = ModelInfo(
        name="test-model:latest", capabilities=capabilities if capabilities is not None else []
    )
    return session, client, provider


async def _collect(session: ChatSession, text: str) -> list:
    return [event async for event in session.send(text)]


# --------------------------------------------------------- reading real pages

async def test_pasted_link_is_fetched_and_given_to_the_model(tmp_path: Path):
    session, client, provider = make_session(tmp_path)
    await _collect(session, "что по ссылке https://obrmos.ru/kur/_9.html ?")

    assert provider.fetched == ["https://obrmos.ru/kur/_9.html"]
    system = client.chat_calls[0]["messages"][0]
    assert system["role"] == "system"
    assert PAGE_TEXT in system["content"]
    assert "https://obrmos.ru/kur/_9.html" in system["content"]


async def test_link_is_read_even_without_tool_support(tmp_path: Path):
    """deepseek-r1 must not be able to block reading by skipping tool calls."""
    session, client, provider = make_session(tmp_path, capabilities=[])
    await _collect(session, "посмотри https://obrmos.ru/kur/_9.html")

    assert provider.fetched == ["https://obrmos.ru/kur/_9.html"]
    assert client.chat_calls[0]["tools"] is None  # nothing offered, page still read
    assert PAGE_TEXT in client.chat_calls[0]["messages"][0]["content"]


async def test_pasted_link_reports_the_source_to_the_ui(tmp_path: Path):
    session, _, _ = make_session(tmp_path)
    events = await _collect(session, "https://obrmos.ru/kur/_9.html")

    results = [e for e in events if isinstance(e, SearchResultEvent)]
    assert len(results) == 1
    assert [s.url for s in results[0].sources] == ["https://obrmos.ru/kur/_9.html"]
    assert results[0].sources[0].snippet  # real page text, shown in the UI
    assert any(isinstance(e, ToolCallEvent) and e.name == "fetch_url" for e in events)


async def test_custom_system_prompt_survives_page_reading(tmp_path: Path):
    """A user's own persona must not be replaced by the link context."""
    client = FakeClient()
    provider = FakeProvider()
    session = ChatSession(
        config=Config(model="test-model:latest", system_prompt="You are a pirate."),
        client=client,
        provider=provider,
        history_store=HistoryStore(directory=tmp_path / "history"),
    )
    session.active_model = ModelInfo(name="test-model:latest", capabilities=[])
    await _collect(session, "https://obrmos.ru/kur/_9.html")

    system = client.chat_calls[0]["messages"][0]["content"]
    assert system.startswith("You are a pirate.")
    assert PAGE_TEXT in system


async def test_message_without_link_fetches_nothing(tmp_path: Path):
    session, client, provider = make_session(tmp_path)
    events = await _collect(session, "привет, как дела?")

    assert provider.fetched == []
    assert not [e for e in events if isinstance(e, SearchResultEvent)]
    assert client.chat_calls[0]["messages"][0]["content"]  # plain system prompt


async def test_duplicate_and_punctuated_links_are_normalised(tmp_path: Path):
    session, _, provider = make_session(tmp_path, capabilities=[])
    await _collect(
        session,
        "смотри https://a.example/x и https://a.example/x, и ещё https://b.example/y.",
    )

    assert provider.fetched == ["https://a.example/x", "https://b.example/y"]


async def test_only_a_few_links_are_read(tmp_path: Path):
    session, _, provider = make_session(tmp_path, capabilities=[])
    urls = " ".join(f"https://site{i}.example/p" for i in range(MAX_AUTO_FETCH + 2))
    await _collect(session, f"страницы: {urls}")

    assert len(provider.fetched) == MAX_AUTO_FETCH


async def test_reading_links_can_be_disabled(tmp_path: Path):
    client = FakeClient()
    provider = FakeProvider()
    session = ChatSession(
        config=Config(model="test-model:latest", web_search_enabled=False),
        client=client,
        provider=provider,
        history_store=HistoryStore(directory=tmp_path / "history"),
    )
    session.active_model = ModelInfo(name="test-model:latest", capabilities=[])
    await _collect(session, "https://obrmos.ru/kur/_9.html")

    assert provider.fetched == []


# ----------------------------------------------------------- tool advertising

async def test_fetch_url_is_offered_alongside_web_search(tmp_path: Path):
    session, client, _ = make_session(tmp_path, capabilities=["tools"])
    await _collect(session, "привет")

    names = [t["function"]["name"] for t in client.chat_calls[0]["tools"]]
    assert names == ["web_search", "fetch_url"]
