"""Session-only administrator login, independent of PHNIX cloud credentials.

No passwords, persistent bearer tokens, or sessions in Git/source/localStorage.
Browser receives an HttpOnly SameSite=Strict cookie. Session lives only in the
FoxAir Python process (expires after eight hours / service restart).
Cookie-authorized requests additionally require a same-origin custom header.
"""
from __future__ import annotations

import secrets
import threading
import time

_COOKIE = "foxair_admin_session"
_TTL = 8 * 3600
_SESSIONS: dict[str, float] = {}
_LOCK = threading.Lock()
_MAX_SESSIONS = 32


def login() -> str:
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _LOCK:
        expired = [key for key, limit in _SESSIONS.items() if limit < now]
        for key in expired:
            _SESSIONS.pop(key, None)
        if len(_SESSIONS) >= _MAX_SESSIONS:
            oldest = min(_SESSIONS, key=_SESSIONS.get)
            _SESSIONS.pop(oldest, None)
        _SESSIONS[token] = now + _TTL
    return token


def authenticated(token: str | None) -> bool:
    if not token or len(token) > 128:
        return False
    now = time.monotonic()
    with _LOCK:
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
            _SESSIONS.pop(token, None)


def session_cookie_name() -> str:
    return _COOKIE
