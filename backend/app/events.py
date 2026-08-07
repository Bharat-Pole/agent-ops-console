"""In-process domain event bus — the CQRS/Pub-Sub seam without the
infrastructure. Subscribers run synchronously in-transaction for v1; a Pub/Sub
adapter can replace `emit` without touching emitters.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

_subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)


def subscribe(event_type: str, handler: Callable[[dict[str, Any]], None]) -> None:
    _subscribers[event_type].append(handler)


def emit(event_type: str, payload: dict[str, Any]) -> None:
    for handler in _subscribers.get(event_type, []):
        handler(payload)
