"""One-time GUI bootstrap, proven by a private per-installation setup code."""

import hmac
import json
import os
import secrets
import threading
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from backend import cloud_config as config

router = APIRouter()
LOCK = threading.RLock()


def required():
    return not config.ADMIN_FILE.exists() and not config._read_json(
        config.STATE_DIR / "users.json"
    ).get("users")


def code_file():
    return config.STATE_DIR / "setup-code.json"


def pending():
    return required() and code_file().exists()


def initialize():
    with LOCK:
        if not required():
            return
        config.STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(
                code_file(),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError:
            return
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"code": secrets.token_urlsafe(32)}, handle)
            handle.flush()
            os.fsync(handle.fileno())


class Complete(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=256)


@router.get("/api/setup/status")
def status(request: Request):
    initialize()
    from backend.lan_access import direct_http

    return {
        "required": required(),
        "container": os.getenv("FOXAIR_CONTAINER") == "1",
        "lan_http": direct_http(request),
    }


@router.post("/api/setup/complete")
def complete(payload: Complete, request: Request):
    config.ensure_secure_origin(request)
    if request.headers.get("x-foxair-admin") != "1":
        raise HTTPException(403, "Anwendungs-Header fehlt")
    peer = request.client.host if request.client else ""
    if not config._check_admin_rate_limit(peer):
        raise HTTPException(429, "Zu viele Versuche; später erneut versuchen")
    with LOCK:
        if not required():
            raise HTTPException(
                409, "Instanz bereits eingerichtet; bestehende Konten bleiben erhalten"
            )
        expected = config._read_json(code_file()).get("code", "")
        valid = bool(expected) and hmac.compare_digest(
            expected.encode("utf-8"), payload.code.encode("utf-8")
        )
        config._admin_attempt_result(peer, valid)
        if not valid or payload.password == payload.code:
            raise HTTPException(403, "Einrichtungscode ungültig")
        record = config.admin_record(payload.password)
        try:
            fd = os.open(
                config.ADMIN_FILE,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError:
            raise HTTPException(409, "Instanz bereits eingerichtet") from None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
            handle.flush()
            os.fsync(handle.fileno())
        code_file().unlink(missing_ok=True)
    return {"configured": True, "login_required": True}


if __name__ == "__main__":
    initialize()
    if not required():
        raise SystemExit(
            "Bereits eingerichtet. Kein Passwort oder Benutzer wurde verändert."
        )
    print("Einmaliger FoxAir-Einrichtungscode (nur in der lokalen GUI verwenden):")
    print(
        config._read_json(code_file()).get(
            "code", "Code-Datei beschädigt; lokale Wiederherstellung erforderlich"
        )
    )
