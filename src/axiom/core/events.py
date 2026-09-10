"""Simple event bus for UI/log integration."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class Event:
    """A UI/agent event."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)


EventHandler = Callable[[Event], None]
AsyncEventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """Tiny synchronous/async event bus.

    Handlers registered with ``subscribe`` are sync; handlers registered
    with ``subscribe_async`` are awaited on the running loop.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._async_handlers: dict[str, list[AsyncEventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def subscribe_async(self, event_type: str, handler: AsyncEventHandler) -> None:
        self._async_handlers[event_type].append(handler)

    def unsubscribe_all(self, event_type: str) -> None:
        self._handlers.pop(event_type, None)
        self._async_handlers.pop(event_type, None)

    def emit(self, event: Event) -> None:
        for handler in list(self._handlers[event.type]):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - handlers must not crash the bus
                pass
        for handler in list(self._async_handlers[event.type]):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(handler(event))
            except RuntimeError:
                pass

    def emit_type(self, event_type: str, **data: Any) -> None:
        self.emit(Event(type=event_type, data=data))
