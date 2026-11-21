"""Private bus configuration and passive Display state/live stream."""

import asyncio
import json
import time
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from backend.cloud_config import require_admin, ensure_secure_origin
from backend.settings import local_bus_config, save_local_bus, standard_endpoint
from backend.rtu import standard_connection
from backend.transport_selection import LOCK, operation
from backend.display_bus import manager
from backend.register_definitions import DASHBOARD_FIELDS

router = APIRouter()
Transport = Literal["display_modbus", "standard_modbus"]


class BusConfig(BaseModel):
    medium: Literal["tcp", "serial"] = "tcp"
    serial_device: str = Field(default="", max_length=255)
    baudrate: int | None = Field(default=None, ge=1200, le=115200)
    host: str = Field(default="", max_length=64)
    port: int = Field(ge=1, le=65535)
    enabled: bool = False
    slave: int = Field(ge=1, le=247)
    timeout: float = Field(default=2, ge=0.25, le=10)
    connection_mode: Literal["browser", "permanent"] = "browser"
    browser_timeout_seconds: int = Field(default=90, ge=30, le=3600)


@router.post("/api/local/{transport}/config")
def config(transport: Transport, request: Request):
    require_admin(request)
    return local_bus_config(transport)


@router.post("/api/local/{transport}/config/save")
def save(transport: Transport, payload: BusConfig, request: Request):
    require_admin(request)
    try:
        with LOCK:
            saved = save_local_bus(transport, **payload.model_dump())
            if transport == "standard_modbus":
                standard_connection.disconnect()
            return saved
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.post("/api/local/standard_modbus/lease")
def standard_lease(request: Request):
    ensure_secure_origin(request)
    if request.headers.get("x-foxair-admin") != "1":
        raise HTTPException(403, "Anwendungs-Header fehlt")
    try:
        with operation("standard_modbus"):
            if standard_endpoint() is not None:
                standard_connection.lease(
                    local_bus_config("standard_modbus")["browser_timeout_seconds"]
                )
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return {"ok": True}


@router.post("/api/local/display_modbus/scan")
def scan(request: Request):
    require_admin(request)
    try:
        return manager.synchronize()
    except ValueError as error:
        raise HTTPException(503, str(error)) from None


@router.post("/api/local/display_modbus/lease")
def lease(request: Request):
    ensure_secure_origin(request)
    if request.headers.get("x-foxair-admin") != "1":
        raise HTTPException(403, "Anwendungs-Header fehlt")
    manager.lease()
    return manager.state()


def local_snapshot(transport="display_modbus"):
    from backend.catalog import load_registers

    definitions = load_registers()
    values = {
        key: {
            **row,
            "name": definitions.get(key, {}).get("name") or f"Register {key}",
            "code": definitions.get(key, {}).get("code") or "",
        }
        for key, row in manager.values().items()
    }
    state = manager.state()
    metrics = {}
    for name, register in DASHBOARD_FIELDS.items():
        row = values.get(str(register))
        if row:
            metrics[name] = {
                **row,
                "quality": "observed"
                if state["connected"] and row["quality"] != "stale"
                else "stale",
            }
    # The live broadcast carries 2014 even before parameter block 1091 (R02).
    # Project it on every SSE update, exactly as on the ordinary dashboard.
    from backend.last_values import fill_dashboard

    metrics = fill_dashboard({"metrics": metrics})["metrics"]
    power = values.get("2011")
    if power and power.get("raw") in (0, 1):
        metrics["power"] = {**power, "source_code": "2011"}
    selected = values.get("2014")
    if (
        selected
        and isinstance(selected.get("value"), (int, float))
        and 5 <= selected["value"] <= 80
    ):
        metrics["target"] = {
            **selected,
            "source_code": "2014",
            "label": "Aktueller Wassersollwert",
        }
    return {
        "values": values,
        "metrics": metrics,
        "connection": {k: v for k, v in state.items() if k != "scan"},
        "scan": state["scan"],
    }


@router.get("/api/local/display_modbus/state")
def snapshot():
    return local_snapshot()


@router.get("/api/local/display_modbus/events")
async def events(request: Request):
    async def stream():
        previous_values = {}
        previous_state = None
        started = time.monotonic()
        first = True
        while not await request.is_disconnected():
            from backend.users import read, principal

            if not read().get("guest_read", True) and (
                not principal(request) or time.monotonic() - started > 60
            ):
                return
            manager.lease()
            snapshot = local_snapshot()
            values = snapshot.pop("values")
            changed = {
                key: row
                for key, row in values.items()
                if previous_values.get(key) != row
            }
            removed = [key for key in previous_values if key not in values]
            if first or changed or removed or snapshot != previous_state:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            **snapshot,
                            "values": changed,
                            "removed": removed,
                            "reset": first,
                        }
                    )
                    + "\n\n"
                )
                previous_values = values
                previous_state = snapshot
                first = False
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
