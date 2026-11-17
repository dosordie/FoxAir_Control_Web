"""LTE cache, scan, lease and one-way register stream endpoints."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from backend.cloud_config import ensure_secure_origin
from backend.settings import warmlink_endpoint
from backend.register_definitions import DASHBOARD_FIELDS

router = APIRouter()


@router.get("/api/last-values")
def last_known_values():
    from backend.last_values import store

    return {"values": store.values()}


@router.get("/api/warmlink/connection")
def bus_connection_state():
    from backend.bus_connection import status, observed_words

    return {**status(), "observed": observed_words()}


def lte_snapshot():
    from backend.bus_connection import register_values, observed_metrics, status
    from backend.register_scan import status as scan_status

    endpoint = warmlink_endpoint()
    from backend.last_values import store, fill_dashboard

    values = {**store.values(), **register_values(endpoint)}
    metrics = fill_dashboard({"metrics": observed_metrics(DASHBOARD_FIELDS, endpoint)})[
        "metrics"
    ]
    return {
        "connection": status(),
        "values": values,
        "metrics": metrics,
        "scan": scan_status(),
    }


@router.get("/api/warmlink/state")
def lte_state():
    return lte_snapshot()


@router.post("/api/warmlink/scan")
def lte_scan(request: Request):
    ensure_secure_origin(request)
    if request.headers.get("x-foxair-admin") != "1":
        raise HTTPException(status_code=403, detail="Anwendungs-Header fehlt")
    from backend.register_scan import start

    try:
        return start()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/api/warmlink/events")
async def lte_events(request: Request):
    import asyncio
    import json

    async def events():
        previous = {}
        previous_state = None
        first = True
        ticks = 0
        while not await request.is_disconnected():
            # Reading this cache never connects to the DTU or sends telegrams.
            snapshot = lte_snapshot()
            values = snapshot.pop("values")
            changed = {
                key: value
                for key, value in values.items()
                if previous.get(key) != value
            }
            removed = [key for key in previous if key not in values]
            if first or changed or removed or snapshot != previous_state:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            **snapshot,
                            "values": changed,
                            "removed": removed,
                            "reset": first,
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                previous = values
                previous_state = snapshot
                first = False
                ticks = 0
            elif ticks >= 30:
                yield ": keepalive\n\n"
                ticks = 0
            ticks += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/api/warmlink/lease")
def bus_browser_lease(request: Request):
    ensure_secure_origin(request)
    if request.headers.get("x-foxair-admin") != "1":
        raise HTTPException(status_code=403, detail="Lebenszeichen-Header fehlt")
    from backend.bus_connection import lease

    return lease()
