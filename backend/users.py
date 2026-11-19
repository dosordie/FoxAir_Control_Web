"""Private local accounts and authorization, independent of browser claims."""

import hashlib
import hmac
import re
import threading
import secrets
from fastapi import HTTPException
from backend import cloud_config as config
from backend.admin_session import session_identity, session_cookie_name

LOCK = threading.RLock()
ROLES = {"reader": 0, "operator": 1, "admin": 2}


def read():
    return config._read_json(config.STATE_DIR / "users.json")


def save(data):
    config._atomic_json(config.STATE_DIR / "users.json", data)


def account(name):
    if name == "admin":
        return (
            {"role": "admin", "enabled": True, "version": "legacy"}
            if config._read_json(config.ADMIN_FILE)
            else None
        )
    row = read().get("users", {}).get(name)
    return (
        row if row and row.get("enabled") is True and row.get("role") in ROLES else None
    )


def principal(request):
    try:
        config.ensure_secure_origin(request)
    except HTTPException:
        return None
    data = session_identity(request.cookies.get(session_cookie_name()))
    if data is None:
        return None
    if not data:
        return {"username": "admin", "role": "admin", "method": "password"}
    name = data.get("account")
    row = account(name)
    if not row:
        return None
    if data.get("provider") == "authelia":
        from backend.proxy_sso import session_matches

        if not session_matches(request, data):
            return None
    elif data.get("provider") != "local" or data.get("version") != row.get("version"):
        return None
    return {"username": name, "role": row["role"], "method": data["provider"]}


def require(request, role="admin"):
    config.ensure_secure_origin(request)
    user = principal(request)
    if (
        request.headers.get("x-foxair-admin") != "1"
        or not user
        or ROLES[user["role"]] < ROLES[role]
    ):
        raise HTTPException(403, "Berechtigung erforderlich")
    return user


def login(request, username, password):
    config.ensure_secure_origin(request)
    peer = request.client.host if request.client else ""
    if not config._check_admin_rate_limit(peer):
        raise HTTPException(429, "Zu viele Anmeldeversuche")
    row = account(username)
    valid = False
    if row:
        record = row.get("password", {})
        try:
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                bytes.fromhex(record["salt"]),
                config.ITERATIONS,
            )
            valid = hmac.compare_digest(digest, bytes.fromhex(record["hash"]))
        except (KeyError, ValueError, TypeError):
            pass
    config._admin_attempt_result(peer, valid)
    if not valid:
        raise HTTPException(403, "Anmeldung fehlgeschlagen")
    return {"provider": "local", "account": username, "version": row["version"]}


def update(username, role, enabled, password, allowed):
    if (
        username == "admin"
        or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.@-]{0,63}", username)
        or role not in ROLES
    ):
        raise HTTPException(
            422, "Ungültiger Benutzer oder Rolle; admin bleibt reserviert"
        )
    if any(not isinstance(n, int) or not 0 <= n <= 65535 for n in allowed):
        raise HTTPException(422, "Ungültige Registerfreigabe")
    with LOCK:
        data = read()
        users = data.setdefault("users", {})
        old = users.get(username, {})
        record = old.get("password")
        if password:
            try:
                record = config.admin_record(password)
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
        users[username] = {
            "role": role,
            "enabled": enabled,
            "password": record,
            "allowed_registers": sorted(set(allowed)),
            "version": secrets.token_hex(16),
        }
        save(data)


def require_operator(request, registers):
    user = require(request, "operator")
    if user["role"] != "admin":
        allowed = account(user["username"]).get("allowed_registers", [])
        if not set(registers).issubset(allowed):
            raise HTTPException(403, "Parameter nicht für diesen Benutzer freigegeben")
    return user
