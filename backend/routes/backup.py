"""Password-encrypted, authenticated backups; never export server secrets or sessions."""

import base64
import hashlib
import json
import secrets
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError
from backend import users, cloud_config, admin_session

router = APIRouter()
FILES = ("users.json", "cloud.json", "warmlink.json")


class Backup(BaseModel):
    password: str = Field(min_length=12, max_length=256)
    archive: str = Field(default="", max_length=2000000)


def cipher(password, salt):
    return Fernet(
        base64.urlsafe_b64encode(
            hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
        )
    )


@router.post("/api/accounts/backup")
def backup(payload: Backup, request: Request):
    users.require(request)
    salt = secrets.token_bytes(32)
    with users.LOCK:
        rows = {
            name: cloud_config._read_json(cloud_config.STATE_DIR / name)
            for name in FILES
        }
    sealed = cipher(payload.password, salt).encrypt(json.dumps(rows).encode()).decode()
    return {"archive": json.dumps({"version": 1, "salt": salt.hex(), "data": sealed})}


@router.post("/api/accounts/restore")
def restore(payload: Backup, request: Request):
    users.require(request)
    try:
        envelope = json.loads(payload.archive)
        salt = bytes.fromhex(envelope["salt"])
        if envelope["version"] != 1 or len(salt) != 32:
            raise ValueError()
        rows = json.loads(
            cipher(payload.password, salt).decrypt(envelope["data"].encode())
        )
        if set(rows) != set(FILES) or any(
            not isinstance(row, dict) for row in rows.values()
        ):
            raise ValueError()
        if rows["warmlink.json"]:
            from backend.main import WarmlinkConfigUpdate

            WarmlinkConfigUpdate.model_validate(rows["warmlink.json"])
        if not isinstance(rows["users.json"].get("users", {}), dict):
            raise ValueError()
        for name, row in rows["users.json"].get("users", {}).items():
            if (
                name == "admin"
                or row.get("role") not in users.ROLES
                or not isinstance(row.get("enabled"), bool)
            ):
                raise ValueError()
        with users.LOCK:
            previous = {
                name: cloud_config._read_json(cloud_config.STATE_DIR / name)
                for name in FILES
            }
            try:
                for name in FILES:
                    cloud_config._atomic_json(cloud_config.STATE_DIR / name, rows[name])
            except OSError:
                for name in FILES:
                    cloud_config._atomic_json(
                        cloud_config.STATE_DIR / name, previous[name]
                    )
                raise
        with admin_session._LOCK:
            admin_session._SESSIONS.clear()
            admin_session._save()
        return {"restored": True, "login_required": True}
    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        InvalidToken,
        ValidationError,
    ):
        raise HTTPException(422, "Sicherung beschädigt oder Passwort falsch") from None
