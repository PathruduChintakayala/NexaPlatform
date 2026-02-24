from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class InternalEvent:
    name: str
    payload: dict[str, Any]


EventHandler = Callable[[InternalEvent], None]


class InProcessEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._subscribers[event_name].append(handler)

    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        event = InternalEvent(name=event_name, payload=payload)
        for handler in self._subscribers.get(event_name, []):
            handler(event)


event_bus = InProcessEventBus()
