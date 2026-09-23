"""Model Router + fallback + cost-aware routing (п.16-17).

Маршрут по типу задачи: simple/coding/reasoning/huge-context/vision/fast.
Fallback: primary -> fallback -> fallback2 на 429/timeout/unavailable.
Budget: performance / balanced / economy.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RouteTarget:
    provider_id: str
    model: str
    reason: str = ""


@dataclass
class RouterConfig:
    enabled: bool = True
    budget: str = "balanced"
    primary: RouteTarget | None = None
    fallbacks: list[RouteTarget] = field(default_factory=list)

    def chain(self) -> list[RouteTarget]:
        out: list[RouteTarget] = []
        if self.primary is not None:
            out.append(self.primary)
        out.extend(self.fallbacks)
        return out


def classify_task(text: str) -> str:
    lowered = (text or "").lower()
    if any(k in lowered for k in ("vision", "image", "скрин", "фото", "картинк", "изображен")):
        return "vision"
    if any(k in lowered for k in ("huge", "long context", "весь проект", "вся кодбаза",
                                  "большой контекст", "много файлов")):
        return "huge-context"
    if any(k in lowered for k in ("reason", "архитектур", "спроектир", "сложн",
                                  "докажи", "алгоритм", "рассужден")):
        return "reasoning"
    if any(k in lowered for k in ("code", "код", "баг", "bug", "исправ", "рефактор",
                                  "функци", "класс", "тест", "debug", "ошибк")):
        return "coding"
    if len(lowered.strip()) < 60:
        return "simple"
    return "fast"


def complexity_of(text: str) -> str:
    words = len((text or "").split())
    if words < 15:
        return "low"
    if words < 60:
        return "medium"
    return "high"


class ModelRouter:
    """Чистый роутер: без сети, только эвристики + каталог моделей."""

    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig()

    def route(self, text: str, catalog=None) -> RouteTarget | None:
        if not self.config.enabled:
            return self.config.primary
        task = classify_task(text)
        complexity = complexity_of(text)
        # Явный primary всегда побеждает, если routing включён «мягко».
        if self.config.primary is not None and task in ("simple", "fast") \
                and self.config.budget != "economy":
            return self.config.primary
        models = list(catalog.all()) if catalog is not None else []
        if not models:
            return self.config.primary

        def _pick(pred, fallback_idx: int = 0) -> RouteTarget | None:
            matches = [m for m in models if pred(m)]
            if not matches:
                return None
            if self.config.budget == "economy":
                matches.sort(key=lambda m: m.id.lower())
            elif self.config.budget == "performance":
                matches.sort(key=lambda m: (not m.reasoning, m.id.lower()))
            chosen = matches[fallback_idx % len(matches)]
            return RouteTarget(chosen.provider_id, chosen.id,
                               reason=f"task={task} complexity={complexity}")

        if task == "vision":
            hit = _pick(lambda m: m.vision)
            if hit:
                return hit
        if task == "huge-context":
            hit = _pick(lambda m: m.long_context)
            if hit:
                return hit
        if task == "reasoning" or (task == "coding" and complexity == "high"):
            hit = _pick(lambda m: m.reasoning)
            if hit:
                return hit
        if task == "coding":
            hit = _pick(lambda m: m.coding or m.tool_calling)
            if hit:
                return hit
        if task == "simple":
            hit = _pick(lambda m: not m.reasoning)
            if hit:
                return hit
        first = models[0]
        return RouteTarget(first.provider_id, first.id, reason=f"task={task} fallback=first")

    def should_fallback(self, error: Exception | str) -> bool:
        if isinstance(error, str):
            text = error.lower()
        else:
            # The real ``kind`` matters: ``ollama_unavailable`` / ``provider_unavailable``
            # never spell "unavailable" in the human-readable message.
            text = f"{type(error).__name__}: {error} {getattr(error, 'kind', '')}".lower()
        markers = ("429", "rate limit", "timeout", "timed out", "unavailable",
                   "connection", "context", "overloaded", "503", "502", "500")
        return any(m in text for m in markers)

    def next_fallback(self, failed: RouteTarget) -> RouteTarget | None:
        chain = self.config.chain()
        for idx, target in enumerate(chain):
            if target.provider_id == failed.provider_id and target.model == failed.model:
                if idx + 1 < len(chain):
                    return chain[idx + 1]
                return None
        return self.config.fallbacks[0] if self.config.fallbacks else None
