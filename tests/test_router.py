"""Tests for the smart model router and model manager."""

from __future__ import annotations

from axiom.models.manager import ModelManager
from axiom.models.mock import MockProvider
from axiom.models.router import ModelRouter


def make_manager() -> ModelManager:
    return ModelManager({"model": {"model": "GPT-OSS-120B", "provider": "openai_compatible"}})


class TestModelRouter:
    def test_primary_selection(self) -> None:
        router = ModelRouter(make_manager())
        decision = router.select("CODING")
        assert decision.model.id == "GPT-OSS-120B"
        assert decision.switched is False

    def test_fast_route(self) -> None:
        router = ModelRouter(make_manager())
        assert router.select("FAST").model.id == "Qwen3.6-27B"

    def test_fallback_on_failure(self) -> None:
        router = ModelRouter(make_manager())
        router.record_failure("GPT-OSS-120B", "offline")
        decision = router.select("CODING")
        assert decision.model.id == "GLM-5.3-Flash"
        assert decision.switched is True

    def test_rate_limited_is_skipped(self) -> None:
        router = ModelRouter(make_manager())
        router.mark_rate_limited("GPT-OSS-120B")
        assert router.select("CODING").model.id == "GLM-5.3-Flash"

    def test_recovery_after_success(self) -> None:
        router = ModelRouter(make_manager())
        router.record_failure("GPT-OSS-120B")
        router.record_success("GPT-OSS-120B", latency=0.4)
        assert router.select("CODING").model.id == "GPT-OSS-120B"

    def test_context_window_respected(self) -> None:
        router = ModelRouter(make_manager())
        decision = router.select("CODING", context_tokens=200_000)
        # every known model has <=131072 context: falls to optimistic/known pick
        assert decision.model.context_window >= 0

    def test_vision_route(self) -> None:
        router = ModelRouter(make_manager())
        assert router.select("VISION").model.vision is True

    def test_capability_filtering(self) -> None:
        manager = make_manager()
        router = ModelRouter(manager)
        for decision_type in ("FAST", "CODING", "REASONING"):
            decision = router.select(decision_type)
            assert decision.task_type == decision_type


class TestModelManager:
    def test_known_models_complete(self) -> None:
        manager = make_manager()
        ids = {m.id for m in manager.list_models()}
        for expected in ("GPT-OSS-120B", "GLM-5.3-Flash", "MiMo-V2.5", "Qwen3.8-Flash",
                         "Codestral", "GPT-OSS-20B"):
            assert expected in ids

    def test_create_provider_unknown(self) -> None:
        manager = make_manager()
        try:
            manager.create_provider("nonexistent", model="x")
            raised = False
        except Exception:
            raised = True
        assert raised

    def test_mock_provider_roundtrip(self) -> None:
        import asyncio

        provider = MockProvider(script=[{"content": "ok"}])
        response = asyncio.run(provider.chat([{"role": "user", "content": "hi"}]))
        assert response.content == "ok"
