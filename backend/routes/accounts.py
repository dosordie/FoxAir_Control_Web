"""Admin-only account, session and audit management."""

import hashlib
import os
import re
from pathlib import Path
import time
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from backend import users, admin_session, cloud_config

router = APIRouter()


class UserUpdate(BaseModel):
    username: str = Field(max_length=64)
    role: str
    enabled: bool = True
    password: str = Field(default="", max_length=256)
    allowed_registers: list[int] = Field(default_factory=list, max_length=1000)


class Policy(BaseModel):
    guest_read: bool = True
    sso_mapping: dict[str, str] = Field(default_factory=dict)


@router.get("/api/accounts")
def listing(request: Request):
    users.require(request)
    data = users.read()
    rows = [
        {
            "username": "admin",
            "role": "admin",
            "enabled": True,
            "allowed_registers": [],
            "fallback": True,
        }
    ]
    rows += [
        {
            "username": name,
            **{key: row.get(key) for key in ("role", "enabled", "allowed_registers")},
        }
        for name, row in data.get("users", {}).items()
    ]
    return {
        "users": rows,
        "guest_read": data.get("guest_read", True),
        "sso_mapping": data.get(
            "sso_mapping",
            cloud_config._read_json(
                Path(
                    os.environ.get(
                        "FOXAIR_SSO_CONFIG", str(cloud_config.STATE_DIR / "sso.json")
                    )
                )
            ).get("user_mapping", {}),
        ),
    }


@router.post("/api/accounts/user")
def update(payload: UserUpdate, request: Request):
    users.require(request)
    users.update(
        payload.username,
        payload.role,
        payload.enabled,
        payload.password,
        payload.allowed_registers,
    )
    return {"saved": True}


@router.post("/api/accounts/policy")
def policy(payload: Policy, request: Request):
    users.require(request)
    if any(
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}", name)
        or not users.account(target)
        for name, target in payload.sso_mapping.items()
    ):
        raise HTTPException(422, "SSO-Zuordnung benötigt vorhandene aktive Benutzer")
    with users.LOCK:
        data = users.read()
        data.update(payload.model_dump())
        users.save(data)
    return {"saved": True}


@router.get("/api/accounts/sessions")
def sessions(request: Request):
    users.require(request)
    current = hashlib.sha256(
        (request.cookies.get(admin_session.session_cookie_name()) or "").encode()
    ).hexdigest()
    with admin_session._LOCK:
        admin_session._restore()
        return {
            "items": [
                {
                    "id": key,
                    "username": value.get("identity", {}).get("account", "admin")
                    if isinstance(value, dict)
                    else "admin",
                    "expires": admin_session._expiry(value),
                    "current": key == current,
                }
                for key, value in admin_session._SESSIONS.items()
            ]
        }


class Revoke(BaseModel):
    id: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post("/api/accounts/sessions/revoke")
def revoke(payload: Revoke, request: Request):
    users.require(request)
    with admin_session._LOCK:
        admin_session._restore()
        admin_session._SESSIONS.pop(payload.id, None)
        blocked = cloud_config._read_json(
            cloud_config.STATE_DIR / "revoked-sessions.json"
        )
        blocked = {key: value for key, value in blocked.items() if value > time.time()}
        blocked[payload.id] = time.time() + 30 * 24 * 3600
        cloud_config._atomic_json(
            cloud_config.STATE_DIR / "revoked-sessions.json", blocked
        )
        admin_session._save()
    return {"revoked": True}


@router.get("/api/accounts/audit")
def audit(request: Request):
    users.require(request)
    return cloud_config._read_json(cloud_config.STATE_DIR / "audit.json") or {
        "items": []
    }
