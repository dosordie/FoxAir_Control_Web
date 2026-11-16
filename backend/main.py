"""FoxAir Web MVP: WarmLink-style dashboard and on-demand standard Modbus reads.

Cloud reading is supported with server-side credentials; writes, live leases,
display and LTE multi-master protocols are not enabled yet.
"""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.catalog import format_raw, load_registers, search_registers, group_counts
from backend.cloud_config import cloud_status, credentials, save_cloud, require_admin
from backend.cloud_read import CloudError, read_dashboard as cloud_dashboard, read_register as cloud_read_register, discover_devices
from backend.rtu import open_rtu
from backend.settings import standard_endpoint, transport_info, TRANSPORTS

app = FastAPI(title="FoxAir Control Web", version="0.1.0", docs_url=None, redoc_url=None)

DASHBOARD_FIELDS = {
    "power": 1011,
    "mode": 2012,
    "flow": 2077,
    "tank": 2047,
    "outdoor": 2048,
    "return": 2035,
    "supply": 2036,
    "target": 1158,
}
# FC03 ranges reduce requests; avoid active probing on the Display/LTE bus.
READ_BLOCKS = ((1011, 1), (1158, 1), (2012, 1), (2035, 14), (2077, 1))
VALID_TRANSPORTS = set(TRANSPORTS)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_transport(transport: str) -> None:
    if transport not in VALID_TRANSPORTS:
        raise HTTPException(status_code=400, detail="Unbekannter Transport")


@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version}


@app.get("/api/transports")
def transports():
    return {"items": transport_info(), "live_supported": True, "cloud_live_interval": 30}


@app.get("/api/register-groups")
def register_groups():
    return {"items": group_counts()}


@app.get("/api/cloud/config")
def cloud_config():
    # Deliberately no username, device code, password or cloud token.
    return cloud_status()


class CloudConfigUpdate(BaseModel):
    admin_password: str = Field(min_length=1, max_length=256)
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(default="", max_length=256)
    device_code: str = Field(min_length=3, max_length=128)


class CloudAdminAction(BaseModel):
    admin_password: str = Field(min_length=1, max_length=256)


@app.post("/api/cloud/config")
def cloud_config_update(payload: CloudConfigUpdate, request: Request):
    require_admin(request, payload.admin_password)
    _, existing_password, _ = credentials()
    try:
        save_cloud(payload.username, payload.password or existing_password, payload.device_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except OSError:
        raise HTTPException(status_code=503, detail="Cloud-Einstellungen können nicht gespeichert werden") from None
    return cloud_status()


@app.post("/api/cloud/devices")
def cloud_devices(payload: CloudAdminAction, request: Request):
    require_admin(request, payload.admin_password)
    try:
        devices = discover_devices()
    except CloudError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"items": devices, "count": len(devices)}



@app.get("/api/registers")
def registers(query: str = "", group: str = Query("", max_length=18),
              limit: int = Query(80, ge=1, le=200)):
    return {"items": search_registers(query, limit, group=group), "catalog_size": len(load_registers())}


@app.get("/api/registers/{register}/read")
def register_read(register: int, transport: str = "cloud"):
    require_transport(transport)
    if transport == "cloud":
        try:
            result = cloud_read_register(register)
        except CloudError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        return {"register": register, **result, "transport": transport,
                "timestamp": now_iso(), "quality": "fresh"}
    if transport != "standard_modbus":
        raise HTTPException(status_code=501, detail="Dieser Transport unterstützt noch keine aktiven Registerreads")
    endpoint = standard_endpoint()
    if endpoint is None:
        raise HTTPException(status_code=503, detail="Standard-Modbus noch nicht konfiguriert")
    definitions = load_registers()
    entry = definitions.get(str(register))
    if entry is None:
        raise HTTPException(status_code=404, detail="Register nicht im Quellkatalog")
    if str(entry.get("mode") or "read").lower() in ("write", "w"):
        raise HTTPException(status_code=403, detail="Register ist nicht lesbar")
    try:
        with open_rtu(endpoint) as session:
            raw = session.read_holding(register, 1)[0]
    except (OSError, ConnectionError, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Modbus-Lesefehler: " + str(exc)) from exc
    value, unit = format_raw(raw, entry)
    return {"register": register, "raw": raw, "value": value, "unit": unit,
            "transport": transport, "timestamp": now_iso(), "quality": "fresh"}


@app.get("/api/dashboard")
def dashboard(transport: str = "cloud", live: bool = False):
    require_transport(transport)
    snapshot = {
        "transport": transport,
        "timestamp": now_iso(),
        "status": "unavailable",
        "error": None,
        "metrics": {name: None for name in DASHBOARD_FIELDS},
        "live_supported": transport == "cloud",
    }
    if transport == "cloud":
        try:
            metrics = cloud_dashboard(live=live)
            for key, item in metrics.items():
                snapshot["metrics"][key] = {**item, "timestamp": snapshot["timestamp"]} if item else None
            count = sum(item is not None for item in snapshot["metrics"].values())
            snapshot["status"] = "online" if count == len(DASHBOARD_FIELDS) else ("partial" if count else "unavailable")
            if not count:
                snapshot["error"] = "Keine unterstützten Cloud-Werte zurückgegeben"
        except CloudError as exc:
            snapshot["error"] = str(exc)
        return snapshot
    if transport != "standard_modbus":
        snapshot["error"] = "Adapter noch nicht implementiert; keine simulierten Gerätewerte"
        return snapshot
    endpoint = standard_endpoint()
    if endpoint is None:
        snapshot["error"] = "Standard-Modbus noch nicht konfiguriert"
        return snapshot
    words: dict[int, int] = {}
    errors: list[str] = []
    try:
        with open_rtu(endpoint) as session:
            for start, count in READ_BLOCKS:
                try:
                    values = session.read_holding(start, count)
                    words.update({start + i: raw for i, raw in enumerate(values)})
                except (OSError, ConnectionError, TimeoutError, ValueError) as exc:
                    errors.append(f"{start}: {exc}")
                    # A failed/incomplete RTU response can desynchronize the stream.
                    # Do not issue further requests on this same TCP connection.
                    break
    except (OSError, ConnectionError, TimeoutError, ValueError) as exc:
        errors.append(str(exc))
    definition = load_registers()
    for name, register in DASHBOARD_FIELDS.items():
        if register in words:
            value, unit = format_raw(words[register], definition.get(str(register), {}))
            snapshot["metrics"][name] = {"value": value, "unit": unit, "raw": words[register],
                                         "timestamp": snapshot["timestamp"], "quality": "fresh"}
    snapshot["status"] = "online" if len(words) > 0 and not errors else ("partial" if words else "unavailable")
    if errors:
        snapshot["error"] = "Modbus-Abfrage nicht vollständig: " + "; ".join(errors)
    return snapshot


# In production: use Vite-built frontend, served from the same origin as the API.
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_fallback(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = (FRONTEND_DIST / path).resolve()
        if path and file.is_file() and file.is_relative_to(FRONTEND_DIST.resolve()):
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def missing_frontend():
        return {"status": "Frontend noch nicht gebaut", "instruction": "cd frontend && npm install && npm run build"}
