"""Thirty-day admin sessions, persisted as token hashes in private server state.

HttpOnly/SameSite cookies and same-origin POST checks remain required.
"""
from __future__ import annotations

import hashlib
from backend.cloud_config import STATE_DIR, _read_json, _atomic_json

SESSION_FILE = STATE_DIR / "admin-sessions.json"

import secrets
import threading
import time

_COOKIE = "foxair_admin_session"
_TTL = 30 * 24 * 3600
_SESSIONS: dict[str, float] = {}
_LOCK = threading.Lock()
_MAX_SESSIONS = 32


def _restore():
    rows = _read_json(SESSION_FILE)
    _SESSIONS.clear()
    _SESSIONS.update({key: value for key, value in rows.items()
                      if isinstance(value, (int, float)) and value > time.time()})


def _save():
    _atomic_json(SESSION_FILE, _SESSIONS)


def login() -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _LOCK:
        _restore()
        expired = [key for key, limit in _SESSIONS.items() if limit < now]
        for key in expired:
            _SESSIONS.pop(key, None)
        if len(_SESSIONS) >= _MAX_SESSIONS:
            oldest = min(_SESSIONS, key=_SESSIONS.get)
            _SESSIONS.pop(oldest, None)
        _SESSIONS[hashlib.sha256(token.encode()).hexdigest()] = now + _TTL
        _save()
    return token


def authenticated(token: str | None) -> bool:
    if not token or len(token) > 128:
        return False
    now = time.time()
    with _LOCK:
        _restore()
        token = hashlib.sha256(token.encode()).hexdigest()
        expiry = _SESSIONS.get(token)
        if expiry is None:
            return False
        if expiry <= now:
            del _SESSIONS[token]
            return False
        return True


def logout(token: str | None) -> None:
    if token:
        with _LOCK:
            _restore()
            _SESSIONS.pop(hashlib.sha256(token.encode()).hexdigest(), None)
            _save()


def session_cookie_name() -> str:
    return _COOKIE
