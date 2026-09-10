"""Smart Model Router: task-type based model selection with fallback chain."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from axiom.core.logging import get_logger
from axiom.core.types import HealthStatus
from axiom.models.manager import ModelManager
from axiom.models.provider import ModelInfo

logger = get_logger("router")

DEFAULT_FALLBACK = [
    "GLM-5.3-Flash", "MiMo-V2.5", "Qwen3.8-Flash", "Qwen3.6-27B",
    "GPT-OSS-20B", "GLM-4.7-Flash", "GLM-4.6V-Flash", "GLM-4.5-Flash",
]


@dataclass
class RouteDecision:
    """Result of a routing decision."""

    model: ModelInfo
    task_type: str
    reason: str = ""
    fallback_chain: list[str] = field(default_factory=list)
    switched: bool = False


class ModelRouter:
    """Selects the best available model for a task type."""

    def __init__(
        self,
        manager: ModelManager,
        routes: dict[str, list[str]] | None = None,
    ) -> None:
        self._manager = manager
        self._routes = routes or {
            "FAST": ["Qwen3.6-27B", "GLM-4.5-Flash", "GPT-OSS-20B"],
            "CODING": ["GPT-OSS-120B", "GLM-5.3-Flash", "GPT-OSS-20B"],
            "REASONING": ["MiMo-V2.5", "GPT-OSS-120B", "GLM-5.3-Flash"],
            "REVIEW": ["GPT-OSS-120B", "GLM-5.3-Flash"],
            "ORCHESTRATOR": ["MiMo-V2.5", "GPT-OSS-120B"],
            "VISION": ["GLM-4.6V-Flash"],
        }
        self._health: dict[str, str] = {}  # model_id -> health
        self._latency: dict[str, float] = {}  # model_id -> seconds
        self._failures: dict[str, float] = {}  # model_id -> last failure ts

    # -- state -----------------------------------------------------------
    def record_health(self, model_id: str, health: str) -> None:
        self._health[model_id] = health

    def record_success(self, model_id: str, latency: float) -> None:
        self._latency[model_id] = latency
        self._health[model_id] = "healthy"
        self._failures.pop(model_id, None)

    def record_failure(self, model_id: str, health: str = "offline") -> None:
        self._health[model_id] = health
        self._failures[model_id] = time.monotonic()

    def mark_rate_limited(self, model_id: str) -> None:
        self.record_failure(model_id, "rate_limited")

    def get_health(self, model_id: str) -> str:
        return self._health.get(model_id, "unknown")

    # -- selection ---------------------------------------------------------
    def _is_available(self, model: ModelInfo) -> bool:
        health = self._health.get(model.id, "")
        if health in ("healthy", "unknown", ""):
            # recently failed models are skipped for 30s
            failure = self._failures.get(model.id)
            if failure is None or time.monotonic() - failure > 30.0:
                return True
        return False

    def select(self, task_type: str = "CODING", context_tokens: int = 0) -> RouteDecision:
        """Choose a model for a task type, honouring health and priority."""
        chain: list[str] = list(self._routes.get(task_type, DEFAULT_FALLBACK))
        chain += [m for m in DEFAULT_FALLBACK if m not in chain]
        primary_id = chain[0] if chain else "GPT-OSS-120B"
        tried: list[str] = []
        for model_id in chain:
            model = self._manager.get_model(model_id)
            if model is None:
                continue
            if context_tokens and model.context_window < context_tokens:
                continue
            if task_type == "VISION" and not model.vision:
                continue
            if not self._is_available(model):
                tried.append(model_id)
                continue
            switched = model_id != primary_id
            reason = "primary model" if not switched else f"fallback (tried: {', '.join(tried) or 'n/a'})"
            return RouteDecision(
                model=model, task_type=task_type, reason=reason,
                fallback_chain=chain, switched=switched,
            )
        # Nothing healthy: return best-priority known model anyway.
        candidates = [m for m in self._manager.list_models() if m.id]
        if candidates:
            best = max(candidates, key=lambda m: m.priority)
            logger.warning("All models unhealthy; using %s optimistically", best.id)
            return RouteDecision(
                model=best, task_type=task_type,
                reason="all fallbacks unhealthy; optimistic selection",
                fallback_chain=chain, switched=True,
            )
        fallback_model = self._manager.get_current_model()
        assert fallback_model is not None
        return RouteDecision(
            model=fallback_model, task_type=task_type,
            reason="no router knowledge; using configured model",
            fallback_chain=chain, switched=True,
        )
