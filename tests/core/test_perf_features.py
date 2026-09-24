"""Tests for the performance features: think levels, keep_alive, warmup,
adaptive context window and selective tool schemas."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from axiom.core.agent import Agent
from axiom.core.benchmark import BenchmarkRunner, BenchmarkScenario
from axiom.core.chat import ChatSession
from axiom.core.config import Config
from axiom.core.events import Message
from axiom.core.history import HistoryStore
from axiom.core.models import ModelInfo
from axiom.core.ollama import OllamaClient
from axiom.core.performance import PerformanceMetrics
from tests.core.test_chat import FakeClient

# ---------------------------------------------------------------- think levels

def _think_with(config: Config, history: list[dict], caps: list[str] | None = None) -> Any:
    from axiom.core.state_machine import GenerationStateMachine
    from axiom.core.tools.registry import ToolRegistry

    agent = Agent(
        OllamaClient(),
        config=config,
        registry=ToolRegistry(),
        machine=GenerationStateMachine(),
    )
    model = ModelInfo(name="m", capabilities=caps if caps is not None else ["thinking", "tools"])
    return agent._think_param(model, history)


def test_think_explicit_config_wins():
    assert _think_with(Config(think="high"), [{"role": "user", "content": "привет"}]) == "high"


def test_thinking_mode_preset_maps_to_level():
    for mode, expected in (("fast", "low"), ("normal", "medium"), ("deep", "high")):
        assert (
            _think_with(Config(thinking_mode=mode), [{"role": "user", "content": "привет"}])
            == expected
        )


def test_think_auto_heuristic_hard_task_deep():
    assert (
        _think_with(Config(), [{"role": "user", "content": "Объясни, почему этот код падает"}])
        == "high"
    )


def test_think_auto_small_talk_low():
    assert _think_with(Config(), [{"role": "user", "content": "привет"}]) == "low"


def test_think_auto_model_without_thinking_is_none():
    assert (
        _think_with(
            Config(),
            [{"role": "user", "content": "почему?"}],
            caps=["tools"],
        )
        is None
    )


# ------------------------------------------------- context window and metrics

def test_context_messages_limits_history(tmp_path: Path):
    cfg = Config(model="test-model:latest", context_messages=4)
    session = ChatSession(config=cfg, client=FakeClient(), history_store=HistoryStore(
        directory=tmp_path / "history"
    ))
    for i in range(10):
        session.conversation.messages.append(Message(role="user", content=f"msg {i}"))
        session.conversation.messages.append(Message(role="assistant", content=f"ans {i}"))
    ctx = session._context_messages()
    assert len(ctx) == 4
    assert ctx[-1]["content"] == "ans 9"


def test_context_auto_narrows_to_known_budget(tmp_path: Path):
    cfg = Config(model="test-model:latest", context_messages=40, num_ctx=1024)
    session = ChatSession(config=cfg, client=FakeClient(), history_store=HistoryStore(
        directory=tmp_path / "history"
    ))
    for _ in range(30):
        session.conversation.messages.append(Message(role="user", content="x" * 400))
        session.conversation.messages.append(Message(role="assistant", content="y" * 400))
    ctx = session._context_messages()
    assert ctx  # never empty
    assert len(ctx) < 60  # narrowed below the context_messages cap
    assert ctx[-1]["content"].startswith("y")  # the newest turn survives
    # The full trajectory stays intact: only the model payload shrinks.
    assert any(event.kind == "context.narrow" for event in session.trajectory.events)


def test_context_not_narrowed_without_a_known_budget(tmp_path: Path):
    cfg = Config(model="test-model:latest", context_messages=40)
    session = ChatSession(config=cfg, client=FakeClient(), history_store=HistoryStore(
        directory=tmp_path / "history"
    ))
    for _ in range(10):
        session.conversation.messages.append(Message(role="user", content="x" * 400))
        session.conversation.messages.append(Message(role="assistant", content="y" * 400))
    ctx = session._context_messages()
    assert len(ctx) == 20  # unknown window → only the real message limit applies


def test_reasoning_traces_stripped_from_context(tmp_path: Path):
    session = ChatSession(
        config=Config(model="test-model:latest"),
        client=FakeClient(),
        history_store=HistoryStore(directory=tmp_path / "history"),
    )
    session.conversation.messages.append(Message(role="user", content="вопрос"))
    session.conversation.messages.append(
        Message(role="assistant", content="ответ", thinking="долгие размышления")
    )
    ctx = session._context_messages()
    assistant = next(m for m in ctx if m["role"] == "assistant")
    assert assistant["content"] == "ответ"
    assert "thinking" not in assistant


def test_metrics_include_ttft_and_load():
    metrics = Agent._metrics(
        {
            "eval_count": 100,
            "eval_duration": 2_000_000_000,
            "load_duration": 1_500_000_000,
        },
        started=0.0,
        ttft_ms=420,
    )
    assert metrics["ttft_ms"] == 420
    assert metrics["load_ms"] == 1500
    assert metrics["tokens_per_second"] == 50.0


# ------------------------------------------------------------------- warmup

async def test_warmup_sends_minimal_chat_request(monkeypatch):
    captured: dict[str, Any] = {}

    class SimpleResponse:
        status_code = 200

    class Wrapper:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return SimpleResponse()

    monkeypatch.setattr(OllamaClient, "_client", lambda self, timeout=None: Wrapper())
    client = OllamaClient(keep_alive="45m")
    assert await client.warmup("gemma4:12b") is True
    assert captured["url"] == "/api/chat"
    assert captured["json"]["model"] == "gemma4:12b"
    assert captured["json"]["stream"] is False
    assert captured["json"]["keep_alive"] == "45m"


async def test_warmup_never_raises_on_transport_error(monkeypatch):
    import httpx

    class BrokenClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(OllamaClient, "_client", lambda self, timeout=None: BrokenClient())
    assert await OllamaClient().warmup("m") is False


async def test_session_warmup_respects_config(tmp_path: Path):
    session = ChatSession(
        config=Config(model="test-model:latest", warmup_model=False),
        client=FakeClient(),
        history_store=HistoryStore(directory=tmp_path / "history"),
    )
    session.active_model = ModelInfo(name="test-model:latest")
    assert await session.warmup_model() is False  # disabled: no request at all


# --------------------------------------------------------------- list_running

async def test_list_running_parses_ps_response(monkeypatch):
    captured: dict[str, str] = {}

    class PsResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "gemma4:12b", "model": "gemma4:12b:latest"}]}

    class PsClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            captured["url"] = url
            return PsResponse()

    monkeypatch.setattr(OllamaClient, "_client", lambda self, timeout=None: PsClient())
    models = await OllamaClient().list_running()
    assert captured["url"] == "/api/ps"
    assert models == [{"name": "gemma4:12b", "model": "gemma4:12b:latest"}]


async def test_list_running_bad_shape_returns_empty_list(monkeypatch):
    class BadResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpected": True}

    class BadClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return BadResponse()

    monkeypatch.setattr(OllamaClient, "_client", lambda self, timeout=None: BadClient())
    # Regression: this used to implicitly return None and crash callers
    # iterating over it with "'NoneType' object is not iterable".
    assert await OllamaClient().list_running() == []


class _BenchmarkSession:
    def __init__(self):
        self.agent = type("A", (), {})()
        self.agent.perf = PerformanceMetrics(model="m", ttft_ms=1.0, finished_ms=2.0)
        self.sent = 0

    async def startup(self):
        return None

    async def send(self, prompt):
        self.sent += 1
        if False:
            yield None


async def test_benchmark_runner_writes_json_cold_warm(tmp_path):
    output = tmp_path / "report.json"
    runner = BenchmarkRunner(lambda: _BenchmarkSession(), [BenchmarkScenario("short", "hello")],
                             repetitions=2, output=output)
    report = await runner.run()
    assert output.exists()
    assert report["runs"][0]["phase"] == "cold"
    assert report["runs"][1]["phase"] == "warm"
    assert report["summary"]["overall"]["count"] == 2
