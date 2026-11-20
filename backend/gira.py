"""Optional read-only Gira subscriptions, reviewed against ioBroker.gira-endpoint."""

import asyncio
import base64
from contextlib import suppress
from datetime import datetime, timezone
import ipaddress
import json
import logging
import re
import binascii
import math
import secrets
from urllib.parse import quote
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from backend import cloud_config

router = APIRouter()


class ObjectConfig(BaseModel):
    key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9@_./:-]+$")
    name: str = Field(min_length=1, max_length=60)
    unit: str = Field(default="", max_length=16)
    text_encoding: Literal["auto", "plain", "utf8", "latin1"] = "auto"


class Config(BaseModel):
    enabled: bool = False
    host: str = Field(default="", max_length=64)
    port: int = Field(default=80, ge=1, le=65535)
    tls: bool = False
    path: str = Field(default="/", max_length=160, pattern=r"^/[^?#\r\n]*$")
    username: str = Field(default="", max_length=128)
    password: str = Field(default="", max_length=256)
    clear_password: bool = False
    auth_header: bool = False
    objects: list[ObjectConfig] = Field(default_factory=list, max_length=24)


def config():
    return {
        **Config().model_dump(),
        **cloud_config._read_json(cloud_config.STATE_DIR / "gira.json"),
    }


@router.post("/api/expert/gira/config")
def private_config(request: Request):
    cloud_config.require_admin(request)
    row = config()
    return {**row, "password": "", "password_configured": bool(row["password"])}


def validate(payload):
    row = payload.model_dump()
    if row["host"] or row["enabled"]:
        addr = ipaddress.ip_address(row["host"].strip())
        if (
            not addr.is_private
            or addr.is_loopback
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise ValueError()
        row["host"] = str(addr)
    for item in row["objects"]:
        key = item["key"].strip()
        item["key"] = "CO@" + (key[3:] if key.casefold().startswith("co@") else key)
    keys = [item["key"].casefold() for item in row["objects"]]
    if len(keys) != len(set(keys)):
        raise ValueError()
    return row


@router.post("/api/expert/gira/save")
def save(payload: Config, request: Request):
    cloud_config.require_admin(request)
    try:
        row = validate(payload)
    except ValueError:
        raise HTTPException(
            422, "Private IP-Adresse und eindeutige Objektschlüssel erforderlich"
        ) from None
    from backend.settings import _config_lock

    with _config_lock:
        if row.pop("clear_password"):
            row["password"] = ""
        elif not row["password"]:
            row["password"] = config()["password"]
        row["revision"] = secrets.token_hex(12)
        cloud_config._atomic_json(cloud_config.STATE_DIR / "gira.json", row)
    return {"saved": True}


def scalar(value, text_encoding="auto"):
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool):
        return "Ein" if value else "Aus"
    if isinstance(value, str):
        try:
            number = float(value)
            if math.isfinite(number):
                return number
        except ValueError:
            pass
        if (
            text_encoding != "plain"
            and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value)
            and len(value) % 4 != 1
        ):
            try:
                raw = base64.b64decode(value + "=" * (-len(value) % 4), validate=True)
                encodings = (
                    ("utf-8",)
                    if text_encoding == "auto"
                    else (("latin-1",) if text_encoding == "latin1" else ("utf-8",))
                )
                for encoding in encodings:
                    try:
                        decoded = raw.decode(encoding)
                        if decoded and all(
                            c.isprintable() or c in "\n\r\t" for c in decoded
                        ):
                            return decoded[:1000]
                    except UnicodeDecodeError:
                        continue
            except (ValueError, binascii.Error):
                pass
        return value[:1000]
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    return None


def updates(payload, allowed):
    """Accept only configured subscriptions and successful scalar values."""
    if not isinstance(payload, dict) or payload.get("code", 0) != 0:
        return {}
    data = payload.get("data")
    entries = []
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        entries = data["items"]
    elif isinstance(data, list):
        entries = data
    elif (
        isinstance(data, dict)
        and isinstance(payload.get("subscription"), dict)
        and payload["subscription"].get("key")
    ):
        entries = [{"key": payload["subscription"]["key"], "data": data}]
    elif isinstance(data, dict) and ("key" in data or "uid" in data):
        entries = [data]
    elif isinstance(data, dict):
        entries = [{"key": key, "data": value} for key, value in data.items()]
    result = {}
    for item in entries:
        if not isinstance(item, dict) or item.get("code", 0) != 0:
            continue
        key = str(item.get("key", item.get("uid", ""))).strip().casefold()
        if not key.startswith("co@"):
            key = "co@" + key
        if key not in allowed:
            continue
        value = scalar(
            item.get("data", item.get("value")),
            allowed.get(key, "auto") if isinstance(allowed, dict) else "auto",
        )
        if value is not None:
            result[key] = value
    return result


class GiraClient:
    def __init__(self):
        self.task = None
        self.revision = None
        self.values = {}
        self.connected = False
        self.error = None

    def snapshot(self):
        cfg = config()
        if not cfg["enabled"]:
            return {"enabled": False, "connected": False, "items": [], "error": None}
        current = cfg.get("revision") == self.revision
        now = datetime.now(timezone.utc)
        items = []
        for index, obj in enumerate(cfg["objects"]):
            row = self.values.get(obj["key"].casefold()) if current else None
            stale = row and (
                not self.connected
                or (now - datetime.fromisoformat(row["timestamp"])).total_seconds()
                > 300
            )
            items.append(
                {
                    "id": index,
                    "name": obj["name"],
                    "unit": obj["unit"],
                    "value": row["value"] if row else None,
                    "timestamp": row["timestamp"] if row else None,
                    "quality": "stale" if stale else "observed" if row else "waiting",
                }
            )
        return {
            "enabled": True,
            "connected": self.connected and current,
            "items": items,
            "error": self.error if current else None,
        }

    async def run(self):
        from websockets.asyncio.client import connect

        logger = logging.getLogger("foxair.gira.websocket")
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        logger.setLevel(logging.CRITICAL)
        backoff = 1
        while True:
            cfg = config()
            if cfg.get("revision") != self.revision:
                self.revision = cfg.get("revision")
                self.values = {}
                self.error = None
            if not cfg["enabled"] or not cfg["objects"]:
                self.connected = False
                await asyncio.sleep(1)
                continue
            token = base64.b64encode(
                (cfg["username"] + ":" + cfg["password"]).encode()
            ).decode()
            host = "[" + cfg["host"] + "]" if ":" in cfg["host"] else cfg["host"]
            uri = f"{'wss' if cfg['tls'] else 'ws'}://{host}:{cfg['port']}{cfg['path']}"
            headers = {}
            if cfg["username"]:
                if cfg["auth_header"]:
                    headers["Authorization"] = "Basic " + token
                else:
                    uri += "?authorization=" + quote(token, safe="")
            try:
                async with connect(
                    uri,
                    additional_headers=headers,
                    proxy=None,
                    open_timeout=5,
                    close_timeout=2,
                    ping_interval=30,
                    ping_timeout=10,
                    max_size=65536,
                    logger=logger,
                ) as ws:
                    self.connected = True
                    from backend.diagnostics import log_event

                    log_event(
                        "gira", "Gira-WebSocket verbunden; lesende Abonnements aktiv"
                    )
                    self.error = None
                    backoff = 1
                    keys = [obj["key"] for obj in cfg["objects"]]
                    # The only application command: no arbitrary calls or writes.
                    await ws.send(
                        json.dumps({"type": "subscribe", "param": {"keys": keys}})
                    )
                    while config().get("revision") == self.revision:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=1)
                        except asyncio.TimeoutError:
                            continue
                        try:
                            payload = json.loads(message)
                        except (ValueError, TypeError):
                            continue
                        if isinstance(payload, dict) and payload.get("code", 0) != 0:
                            self.error = "Gira-Endpunkt hat eine Anfrage abgelehnt"
                        items = (
                            payload.get("data", {}).get("items", [])
                            if isinstance(payload, dict)
                            and isinstance(payload.get("data"), dict)
                            else []
                        )
                        if isinstance(items, list) and any(
                            isinstance(item, dict) and item.get("code", 0) != 0
                            for item in items
                        ):
                            self.error = (
                                "Einzelne Gira-Objekte konnten nicht abonniert werden"
                            )
                        for key, value in updates(
                            payload,
                            {
                                obj["key"].casefold(): obj.get("text_encoding", "auto")
                                for obj in cfg["objects"]
                            },
                        ).items():
                            self.values[key] = {
                                "value": value,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
            except asyncio.CancelledError:
                raise
            except Exception:
                from backend.diagnostics import log_event

                log_event(
                    "gira-error",
                    "Gira-Verbindung unterbrochen; erneuter Verbindungsversuch folgt",
                )
                self.error = (
                    "Gira-Verbindung nicht verfügbar; erneuter Verbindungsversuch folgt"
                )
            finally:
                self.connected = False
            await asyncio.sleep(backoff)
            backoff = min(30, backoff * 2)

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task


client = GiraClient()


@router.get("/api/expert/gira/state")
def state():
    return client.snapshot()
