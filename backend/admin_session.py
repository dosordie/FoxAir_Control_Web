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
_SESSIONS: dict[str, float | dict] = {}
_LOCK = threading.Lock()
_MAX_SESSIONS = 32


def _restore():
    rows = _read_json(SESSION_FILE)
    _SESSIONS.clear()
    for key, value in rows.items():
        expiry = value.get("expires") if isinstance(value, dict) else value
        if isinstance(expiry, (int, float)) and expiry > time.time():
            if not isinstance(value, dict) or isinstance(value.get("identity"), dict):
                _SESSIONS[key] = value


def _save():
    _atomic_json(SESSION_FILE, _SESSIONS)


def login(identity: dict | None = None) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _LOCK:
        _restore()
        if len(_SESSIONS) >= _MAX_SESSIONS:
            oldest = min(_SESSIONS, key=lambda key: _expiry(_SESSIONS[key]))
            _SESSIONS.pop(oldest, None)
        _SESSIONS[hashlib.sha256(token.encode()).hexdigest()] = (
            {"expires": now + _TTL, "identity": identity} if identity else now + _TTL
        )
        _save()
    return token


def _expiry(value: float | dict) -> float:
    return value["expires"] if isinstance(value, dict) else value


def session_identity(token: str | None) -> dict | None:
    """None means absent/expired; {} is a legacy password-authenticated session."""
    if not token or len(token) > 128:
        return None
    with _LOCK:
        _restore()
        value = _SESSIONS.get(hashlib.sha256(token.encode()).hexdigest())
        if value is None or _expiry(value) <= time.time():
            return None
        return dict(value["identity"]) if isinstance(value, dict) else {}


def authenticated(token: str | None) -> bool:
    return session_identity(token) is not None


def logout(token: str | None) -> None:
    if token:
        with _LOCK:
            _restore()
            _SESSIONS.pop(hashlib.sha256(token.encode()).hexdigest(), None)
            _save()


def session_cookie_name() -> str:
    return _COOKIE
