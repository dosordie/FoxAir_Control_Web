"""Public endpoint serialization shared by the standard and LTE transports."""

import threading

from backend.settings import Endpoint

_guard = threading.Lock()
_locks: dict[tuple, threading.Lock] = {}


def endpoint_lock(endpoint: Endpoint) -> threading.Lock:
    """All clients of a physical TCP endpoint share exactly one operation lock."""
    with _guard:
        return _locks.setdefault(endpoint.connection_key(), threading.Lock())
