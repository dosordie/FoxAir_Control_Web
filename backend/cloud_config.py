"""Protected local cloud settings and admin-password verification.

No credentials/identifiers are stored in the public repository or returned by
any GET API. Admin mutations require a separately configured password and a
HTTPS (or server-loopback) request. This is NOT a replacement for app-wide auth.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
import threading
from typing import Any


STATE_DIR = Path(os.environ.get("FOXAIR_STATE_DIR", "/var/lib/foxair-web"))
CLOUD_FILE = STATE_DIR / "cloud.json"
ADMIN_FILE = STATE_DIR / "admin.json"
ITERATIONS = 320_000
FIELDS = ("FOXAIR_CLOUD_USER", "FOXAIR_CLOUD_PASSWORD", "FOXAIR_CLOUD_DEVICE_CODE")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            return {}
        item = json.loads(path.read_text(encoding="utf-8"))
        return item if isinstance(item, dict) else {}
    except (OSError, ValueError):
        return {}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Own directory state is private to the service account.
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".foxair-", dir=path.parent)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def credentials() -> tuple[str, str, str]:
    managed = _read_json(CLOUD_FILE)
    # Managed config takes precedence; previously configured systemd env
    # remains a fallback until the user migrates through the web UI.
    values = [
        str(managed.get(key, os.environ.get(key, "")) or "")
        for key in FIELDS
    ]
    return values[0].strip(), values[1], values[2].strip()


def cloud_status() -> dict[str, Any]:
    username, password, device = credentials()
    return {
        "configured": bool(username and password and device),
        "username_configured": bool(username),
        "password_configured": bool(password),
        "device_configured": bool(device),
        "storage": "web" if CLOUD_FILE.is_file() else ("systemd" if username else "none"),
        # Do not reveal any portion of an account name, code, password or token.
        "admin_enabled": bool(_read_json(ADMIN_FILE)),
    }


def _validate_account(username: str, password: str, device: str) -> None:
    if not (1 <= len(username) <= 160) or any(x in username for x in ("\r", "\n", "\x00")):
        raise ValueError("Ungültiger Benutzername")
    if not (1 <= len(password) <= 256) or any(x in password for x in ("\r", "\n", "\x00")):
        raise ValueError("Ungültiges Passwort")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{3,128}", device):
        raise ValueError("Ungültige Gerätekennung")


def save_cloud(username: str, password: str, device: str) -> None:
    _validate_account(username, password, device)
    _atomic_json(CLOUD_FILE, dict(zip(FIELDS, (username, password, device))))


def admin_record(password: str) -> dict[str, Any]:
    if len(password) < 12:
        raise ValueError("Admin-Passwort muss mindestens 12 Zeichen enthalten")
    salt = secrets.token_bytes(24)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return {"version": 1, "iterations": ITERATIONS, "salt": salt.hex(), "hash": digest.hex()}


def set_admin_password(password: str) -> None:
    _atomic_json(ADMIN_FILE, admin_record(password))


def verify_admin(password: str) -> bool:
    item = _read_json(ADMIN_FILE)
    if not item or not password:
        return False
    try:
        iterations = int(item["iterations"])
        if not 200_000 <= iterations <= 1_000_000:
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            bytes.fromhex(item["salt"]), iterations,
        )
        return hmac.compare_digest(computed, bytes.fromhex(item["hash"]))
    except (KeyError, ValueError, TypeError):
        return False


_admin_lock = threading.Lock()
_failed_admin_attempts: dict[str, list[float]] = {}


def _check_admin_rate_limit(peer: str) -> bool:
    now = time.monotonic()
    with _admin_lock:
        # Bound memory and reject repeated password guesses for one IP.
        for client in list(_failed_admin_attempts):
            _failed_admin_attempts[client] = [
                t for t in _failed_admin_attempts[client] if now - t < 60
            ]
            if not _failed_admin_attempts[client]:
                del _failed_admin_attempts[client]
        return len(_failed_admin_attempts.get(peer, [])) < 5


def _admin_attempt_result(peer: str, success: bool) -> None:
    with _admin_lock:
        if success:
            _failed_admin_attempts.pop(peer, None)
        else:
            if len(_failed_admin_attempts) < 256 or peer in _failed_admin_attempts:
                _failed_admin_attempts.setdefault(peer, []).append(time.monotonic())


def require_admin(request: "Request", password: str) -> None:
    # Imported lazily, so admin bootstrap works with system Python (no FastAPI).
    from fastapi import HTTPException
    # Refuse transmitting the admin password over plain HTTP on the LAN.
    peer = request.client.host if request.client else ""
    trusted = {x.strip() for x in os.environ.get("FOXAIR_TRUSTED_PROXY_IPS", "").split(",") if x.strip()}
    via_proxy_https = (peer in trusted and
                       request.headers.get("x-forwarded-proto", "").lower() == "https")
    secure = (request.url.scheme == "https" or
              peer in ("127.0.0.1", "::1") or via_proxy_https)
    if not secure:
        raise HTTPException(status_code=403, detail="Administration nur über HTTPS oder SSH-Tunnel (Loopback)")
    # Same-origin check against browser-facing host. X-Forwarded-Host is only
    # accepted from an explicit trusted reverse proxy.
    host = request.headers.get("host", "")
    if via_proxy_https and request.headers.get("x-forwarded-host"):
        host = request.headers["x-forwarded-host"]
    external_scheme = "https" if via_proxy_https else request.url.scheme
    origin = request.headers.get("origin")
    expected = f"{external_scheme}://{host}".rstrip("/")
    if origin and origin.rstrip("/") != expected:
        raise HTTPException(status_code=403, detail="Unzulässiger Origin")
    if not _check_admin_rate_limit(peer):
        raise HTTPException(status_code=429, detail="Zu viele fehlgeschlagene Anmeldeversuche")
    valid = verify_admin(password)
    _admin_attempt_result(peer, valid)
    if not valid:
        raise HTTPException(status_code=403, detail="Administrationspasswort fehlt oder ist ungültig")
