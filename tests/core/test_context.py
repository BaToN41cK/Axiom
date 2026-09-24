"""Tests for ContextManager (axiom.core.context)."""

from __future__ import annotations

from typing import Any

from axiom.core.context import ContextManager


async def fake_summarise(prompt: str) -> str:
    """A minimal summary model stub."""
    return "Summarised: " + prompt[:50]


async def fake_empty_summarise(prompt: str) -> str:
    return ""


class TestEstimate:
    def test_empty_messages(self):
        ctx = ContextManager(max_tokens=4096)
        assert ctx.estimate([]) == 0

    def test_simple_messages(self):
        ctx = ContextManager(max_tokens=4096)
        msgs = [{"role": "user", "content": "hello world"}]
        # "hello world" = 11 chars / 4 ≈ 2.75 → int to 2
        assert ctx.estimate(msgs) >= 1

    def test_dict_and_message_objects(self):
        from axiom.core.events import Message

        ctx = ContextManager(max_tokens=4096)
        mixed: list[Any] = [
            {"role": "user", "content": "a" * 100},
            Message(role="assistant", content="b" * 100),
        ]
        est = ctx.estimate(mixed)
        assert est >= 40  # 200 chars / 4 = 50


class TestPrepare:
    def test_prepare_empty_messages(self):
        ctx = ContextManager(max_tokens=4096)
        result = ctx.prepare([])
        assert result == []

    def test_prepare_with_system_prompt(self):
        ctx = ContextManager(max_tokens=4096)
        result = ctx.prepare(
            [{"role": "user", "content": "hi"}],
            system_prompt="You are AXIOM.",
        )
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are AXIOM."
        assert result[1]["content"] == "hi"

    def test_prepare_trims_when_exceeding_limit(self):
        ctx = ContextManager(max_tokens=100)  # very small
        many_messages = [{"role": "user", "content": "x" * 50}] * 20
        result = ctx.prepare(many_messages)
        # All 20 would be 20*50=1000 chars → 250 tokens >> 75 limit, so trimmed
        assert len(result) < 20
        assert ctx.report.compacted is False  # prepare only drops, summarise compacts


class TestSummarise:
    async def test_no_messages(self):
        ctx = ContextManager()
        summary = await ctx.summarise([])
        assert summary is None

    async def test_no_summary_model(self):
        ctx = ContextManager()
        summary = await ctx.summarise([{"role": "user", "content": "hello"}])
        assert summary is None

    async def test_returns_summary(self):
        ctx = ContextManager()
        summary = await ctx.summarise(
            [{"role": "user", "content": "Hello, what is AI?"}],
            summary_model=fake_summarise,
        )
        assert summary is not None
        assert "Summarised:" in summary

    async def test_empty_summary_is_none(self):
        ctx = ContextManager()
        summary = await ctx.summarise(
            [{"role": "user", "content": "hello"}],
            summary_model=fake_empty_summarise,
        )
        assert summary is None

    async def test_summary_model_exception(self):
        async def failing(_: str) -> str:
            raise RuntimeError("model down")

        ctx = ContextManager()
        summary = await ctx.summarise(
            [{"role": "user", "content": "hello"}],
            summary_model=failing,
        )
        assert summary is None  # graceful fallback


class TestCompact:
    def test_no_summary_drops_old_messages(self):
        ctx = ContextManager()
        msgs = [
            {"role": "user", "content": f"msg {i}"} for i in range(10)
        ]
        compacted = ctx.compact(msgs, None, preserve_count=3)
        assert len(compacted) <= 3 + 1  # might get summary slot
        assert ctx.report.compacted is True

    def test_with_summary_injects_system_message(self):
        ctx = ContextManager()
        msgs = [
            {"role": "user", "content": f"msg {i}"} for i in range(10)
        ]
        compacted = ctx.compact(msgs, "Previous conversation summary...", preserve_count=3)
        # First message is the summary system message
        assert compacted[0]["role"] == "system"
        assert "summary" in compacted[0]["content"].lower()
        # Should have summary + 3 recent
        assert len(compacted) <= 4
        assert ctx.report.compacted is True
        assert ctx.report.summarised_count == 7

    def test_preserved_count_respected(self):
        ctx = ContextManager()
        msgs = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        compacted = ctx.compact(msgs, None, preserve_count=2)
        assert len(compacted) <= 3


class TestIntegration:
    async def test_full_cycle(self):
        ctx = ContextManager(max_tokens=1000)
        msgs = [{"role": "user", "content": "x" * 200}] * 10  # 2000 chars → 500 tokens

        result = ctx.prepare(msgs)
        # 2000 chars ≈ 500 tokens, limit is 750 (75% of 1000)
        # So no trimming needed
        assert len(result) == 10
        assert ctx.should_compact is False

        # Now with massive conversation that should trigger trimming
        many = [{"role": "user", "content": "x" * 500}] * 20  # 10000 chars ≈ 2500 tokens
        ctx2 = ContextManager(max_tokens=1000)
        result2 = ctx2.prepare(many)
        assert len(result2) < 20  # should have trimmed

        summary = await ctx2.summarise(many[:10], summary_model=fake_summarise)
        assert summary is not None

        compacted = ctx2.compact(many, summary, preserve_count=4)
        assert compacted[0]["role"] == "system"
        assert "Summarised:" in compacted[0]["content"]
        assert len(compacted) <= 5
