"""Opt-in Authelia identity verification; no client header grants a role by itself."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re

from fastapi import HTTPException, Request
from backend import cloud_config

SECRET_HEADER = "X-FoxAir-SSO-Secret"
OPTOUT_COOKIE = "foxair_sso_logged_out"
_USER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}\Z")


@dataclass(frozen=True)
class Identity:
    subject: str
    account: str
    binding: str

    def session_data(self) -> dict:
        return {
            "provider": "authelia",
            "subject": self.subject,
            "account": self.account,
            "binding": self.binding,
        }


def _local_admin_exists() -> bool:
    row = cloud_config._read_json(cloud_config.ADMIN_FILE)
    try:
        return (
            row.get("version") == 1
            and 200_000 <= int(row["iterations"]) <= 1_000_000
            and len(bytes.fromhex(row["salt"])) >= 16
            and len(bytes.fromhex(row["hash"])) == 32
        )
    except (KeyError, TypeError, ValueError):
        return False


def verified_identity(request: Request) -> Identity | None:
    """Fail closed, including when run under an unsupported ASGI entry point.

    Only backend.server captures the TCP peer, with Uvicorn's rewriting disabled.
    Forwarded-For, Remote-Addr and groups never participate in this decision.
    Config errors intentionally do not include values in responses or logs.
    """
    try:
        path = Path(
            os.environ.get(
                "FOXAIR_SSO_CONFIG", str(cloud_config.STATE_DIR / "sso.json")
            )
        )
        config = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or config.get("enabled") is not True:
            return None
        if config.get("provider") != "authelia":
            return None
        peer = request.scope.get("foxair.tcp_peer")
        if not peer or not request.client or peer != request.client.host:
            return None
        proxies = config.get("trusted_proxy_ips")
        if not isinstance(proxies, list) or not proxies:
            return None
        trusted = {ipaddress.ip_address(value) for value in proxies}
        if ipaddress.ip_address(peer) not in trusted:
            return None
        secret_env = config.get("shared_secret_env", "FOXWEB_SSO_SECRET")
        if not isinstance(secret_env, str) or not re.fullmatch(
            r"[A-Z][A-Z0-9_]{0,127}", secret_env
        ):
            return None
        secret = os.environ.get(secret_env, "")
        if (
            len(secret) < 43
            or len(set(secret)) < 16
            or not secret.isascii()
            or not secret.isprintable()
        ):
            return None
        supplied = request.headers.getlist(SECRET_HEADER)
        if len(supplied) != 1 or not hmac.compare_digest(
            supplied[0].encode(), secret.encode()
        ):
            return None
        if request.headers.getlist("X-FoxAir-SSO-Authenticated") != ["1"]:
            return None
        header = config.get("username_header", "Remote-User")
        if not isinstance(header, str) or not re.fullmatch(
            r"(?:Remote-User|X-[A-Za-z0-9-]+)", header, re.I
        ):
            return None
        if header.lower() == SECRET_HEADER.lower():
            return None
        users = request.headers.getlist(header)
        if len(users) != 1 or not _USER.fullmatch(users[0]):
            return None
        for name in {
            "Remote-User",
            "Remote-Name",
            "Remote-Email",
            "Remote-Groups",
            header,
        }:
            values = request.headers.getlist(name)
            if len(values) > 1 or any(
                len(v) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in v)
                for v in values
            ):
                return None
        if (
            header.lower() != "remote-user"
            and request.headers.get("remote-user", users[0]) != users[0]
        ):
            return None
        from backend.users import account, read

        mapping = read().get("sso_mapping", config.get("user_mapping"))
        target = mapping.get(users[0]) if isinstance(mapping, dict) else None
        if (
            not isinstance(target, str)
            or not account(target)
            or (target == "admin" and not _local_admin_exists())
        ):
            return None
        # Reuse the existing HTTPS and Origin boundary. This requires the proxy
        # to be explicitly trusted for HTTPS forwarding as well as SSO.
        if not cloud_config.ensure_secure_origin(request):
            return None
        binding = hashlib.sha256(
            json.dumps(config, sort_keys=True).encode() + secret.encode()
        ).hexdigest()
        return Identity(users[0], target, binding)
    except (OSError, ValueError, TypeError, AttributeError, HTTPException):
        # Secure-origin rejection must not turn LAN fallback into a server error.
        return None


def session_matches(request: Request, data: dict) -> bool:
    identity = verified_identity(request)
    return identity is not None and data == identity.session_data()
