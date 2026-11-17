"""Bounded, redacted events shared by Cloud and local transports."""

from collections import deque
from datetime import datetime, timezone
import threading
from typing import Any

_lock = threading.Lock()
_events: deque[dict[str, Any]] = deque(maxlen=150)


def log_event(kind: str, message: str, *, count: int | None = None) -> None:
    """Use fixed application messages/counts, never credentials or API bodies."""
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "message": message,
    }
    if count is not None:
        event["count"] = count
    with _lock:
        _events.appendleft(event)


def logs() -> list[dict[str, Any]]:
    with _lock:
        return list(_events)
