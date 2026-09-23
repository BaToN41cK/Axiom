"""Event Bus — внутренние события harness (п.6).

UI, logging, agents, plugins и telemetry подписываются на события,
а не дёргают друг друга напрямую.
"""
from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable

# Каноничные имена событий harness.
AGENT_CREATED = "agent.created"
AGENT_STARTED = "agent.started"
AGENT_STEP = "agent.step"
AGENT_FAILED = "agent.failed"
MODEL_REQUEST = "model.request"
MODEL_RESPONSE = "model.response"
TOOL_BEFORE = "tool.before"
TOOL_AFTER = "tool.after"
FILE_CHANGED = "file.changed"
TEST_STARTED = "test.started"
TEST_FINISHED = "test.finished"
TRAJECTORY_APPEND = "trajectory.append"


class EventBus:
    """Минимальный pub/sub: sync + async подписчики, best-effort emit."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable]] = defaultdict(list)
        self._emitted = 0

    def subscribe(self, event: str, handler: Callable) -> Callable:
        """Подписаться; возвращает callable для отписки."""
        self._subs[event].append(handler)

        def _off() -> None:
            try:
                self._subs[event].remove(handler)
            except ValueError:
                pass

        return _off

    def unsubscribe(self, event: str, handler: Callable) -> None:
        try:
            self._subs[event].remove(handler)
        except ValueError:
            pass

    @property
    def emitted(self) -> int:
        return self._emitted

    def emit(self, event: str, payload: dict | None = None) -> None:
        """Синхронный emit: async-подписчики игнорируются (см. emit_async)."""
        self._emitted += 1
        data = dict(payload or {})
        data.setdefault("event", event)
        data.setdefault("ts", time.time())
        for handler in list(self._subs.get(event, [])):
            try:
                result = handler(data)
                # Если подписчик async — здесь не await; для await используйте emit_async.
                if result is not None and hasattr(result, "__await__"):
                    try:
                        result.close()  # type: ignore[attr-defined]
                    except Exception:
                        pass
            except Exception:
                continue

    async def emit_async(self, event: str, payload: dict | None = None) -> None:
        self._emitted += 1
        data = dict(payload or {})
        data.setdefault("event", event)
        data.setdefault("ts", time.time())
        for handler in list(self._subs.get(event, [])):
            try:
                result = handler(data)
                if result is not None and hasattr(result, "__await__"):
                    await result
            except Exception:
                continue
