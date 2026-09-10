"""Tests for the ContextManager (token budget + compaction)."""

from __future__ import annotations

import pytest

from axiom.agent.context import ContextManager, estimate_tokens


class TestContextManager:
    def test_estimate_tokens(self) -> None:
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("abcdefgh") == 2

    def test_stats(self) -> None:
        cm = ContextManager(budget=100_000)
        cm.add({"role": "user", "content": "x" * 4000})
        stats = cm.stats()
        assert stats.used > 0
        assert stats.percent < 50.0
        assert stats.used >= 1000

    @pytest.mark.asyncio
    async def test_compact_when_over_budget(self) -> None:
        cm = ContextManager(budget=100)
        cm.add({"role": "system", "content": "system instructions " * 20})
        cm.add({"role": "user", "content": "hi there " * 50})
        cm.add({"role": "tool", "content": "tool output " * 50})
        compacted = cm.maybe_compact()
        assert compacted is True
        assert cm.compacted_count == 1
        assert any(m.get("role") == "system" for m in cm.messages)

    def test_render_task_block(self) -> None:
        cm = ContextManager()
        cm.set_task("fix the login")
        block = cm.render_task_block("Python project")
        assert "Axiom" in block
        assert "Python project" in block
        assert "fix the login" in block
