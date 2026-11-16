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
from backend.cloud_state import (catalog as full_cloud_catalog, value_rows as cloud_values,
    scan_start as cloud_scan_start, logs as cloud_logs, log_event as cloud_log_event)
from backend.cloud_read import CloudError, read_dashboard as cloud_dashboard, cached_dashboard, read_register as cloud_read_register, discover_devices, selected_device_status
from backend.cloud_dialogs import definitions as cloud_dialog_definitions, refresh as refresh_cloud_dialog
from backend.web_update import status as web_update_status, request_update as web_request_update
from backend.rtu import open_rtu
from backend.settings import standard_endpoint, transport_info, TRANSPORTS

app = FastAPI(title="FoxAir Control Web", version="0.1.0", docs_url=None, redoc_url=None)

DASHBOARD_FIELDS = {
    "power": 1011,
    "mode": 2012,
    "flow": 2077,
    "tank": 2047,
    "outdoor": 2048,
    "return": 2045,
    "supply": 2046,
    "target": 1158,
    "base_target": 1158,
}
# FC03 ranges reduce requests; avoid active probing on the Display/LTE bus.
READ_BLOCKS = ((1011, 1), (1158, 1), (2012, 3), (2035, 14), (2077, 1))
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
    username: str = Field(default="", max_length=160)
    password: str = Field(default="", max_length=256)
    device_code: str = Field(default="", max_length=128)


class CloudAdminAction(BaseModel):
    admin_password: str = Field(min_length=1, max_length=256)


@app.post("/api/cloud/config")
def cloud_config_update(payload: CloudConfigUpdate, request: Request):
    require_admin(request, payload.admin_password)
    existing_username, existing_password, existing_device = credentials()
    try:
        save_cloud(payload.username or existing_username, payload.password or existing_password,
                   payload.device_code or existing_device)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except OSError:
        raise HTTPException(status_code=503, detail="Cloud-Einstellungen können nicht gespeichert werden") from None
    return cloud_status()


@app.post("/api/cloud/account")
def cloud_account(payload: CloudAdminAction, request: Request):
    require_admin(request, payload.admin_password)
    username, _, code = credentials()
    # Only disclose these identifying values after checking the admin password.
    cloud_log_event("admin", "Cloud-Kontodaten im Adminbereich geöffnet")
    return {"username": username, "device_code": code}


@app.get("/api/cloud/logs")
def get_cloud_logs():
    return {"items": cloud_logs()}


@app.get("/api/cloud/values")
def get_cloud_values():
    return cloud_values()


@app.post("/api/cloud/scan")
def scan_cloud_catalog(payload: CloudAdminAction, request: Request):
    require_admin(request, payload.admin_password)
    try:
        return cloud_scan_start(force=True)
    except CloudError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/cloud/devices")
def cloud_devices(payload: CloudAdminAction, request: Request):
    require_admin(request, payload.admin_password)
    try:
        devices = discover_devices()
    except CloudError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"items": devices, "count": len(devices)}



@app.post("/api/cloud/device-status")
def cloud_device_status(payload: CloudAdminAction, request: Request):
    require_admin(request, payload.admin_password)
    try:
        return {"status": selected_device_status()}
    except CloudError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/api/cloud/dialogs")
def cloud_dialogs():
    return {"items": cloud_dialog_definitions()}


@app.post("/api/cloud/dialogs/{dialog_id}/refresh")
def cloud_dialog_refresh(dialog_id: str):
    try:
        return refresh_cloud_dialog(dialog_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Spezialdialog nicht vorhanden") from None
    except CloudError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/api/update/status")
def update_status():
    return web_update_status()


@app.post("/api/update/request")
def update_request(payload: CloudAdminAction, request: Request):
    require_admin(request, payload.admin_password)
    try:
        result = web_request_update()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    cloud_log_event("update", "FoxAir-Web-Update angefordert")
    return result


@app.get("/api/registers")
def registers(query: str = "", group: str = Query("", max_length=18),
              limit: int = Query(80, ge=1, le=200)):
    items = search_registers(query, limit, group=group)
    if group.upper() == "CLOUD":
        # Cloud-only entries are queried via /api/cloud/values instead.
        return {"items": [], "catalog_size": len(load_registers())}
    if items:
        cloud_snapshot = cloud_values()
        by_reg: dict[int, dict] = {}
        for cloud_row in cloud_snapshot.get("items", []):
            reg = cloud_row.get("register")
            if not isinstance(reg, int) or cloud_row.get("value") is None:
                continue
            old = by_reg.get(reg)
            if old is None or (cloud_row.get("confidence") == "confirmed"
                               and old.get("confidence") != "confirmed"):
                by_reg[reg] = cloud_row
        for row in items:
            match = by_reg.get(row["register"])
            row["cloud"] = {
                "code": match["code"], "value": match["value"],
                "unit": match.get("unit") or row.get("unit") or "",
                "timestamp": match["timestamp"],
                "quality": match["quality"],
            } if match else None
    return {"items": items, "catalog_size": len(load_registers())}


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
                snapshot["metrics"][key] = {**item, "timestamp": item.get("timestamp") or snapshot["timestamp"]} if item else None
            count = sum(item is not None for item in snapshot["metrics"].values())
            snapshot["status"] = "online" if count == len(DASHBOARD_FIELDS) else ("partial" if count else "unavailable")
            if not count:
                snapshot["error"] = "Keine unterstützten Cloud-Werte zurückgegeben"
            # First successful dashboard read starts a background full catalog
            # scan; subsequent page loads use the same in-memory cache.
            try:
                cloud_scan_start()
            except CloudError:
                pass  # Dashboard remains useful without an optional full scan.
        except CloudError as exc:
            cloud_log_event("error", "Cloud-Übersicht konnte nicht gelesen werden")
            # Never synthesize a live online state from cached values. The
            # original timestamps and explicit stale quality are preserved.
            for key, item in cached_dashboard().items():
                if key in snapshot["metrics"] and item:
                    snapshot["metrics"][key] = item
            snapshot["error"] = str(exc) + " · letzte bekannte Werte (veraltet)"
            snapshot["status"] = "unavailable"
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
    if 2014 in words:
        selected, unit = format_raw(words[2014], definition.get("2014", {}))
        try:
            valid = 5 <= float(selected) <= 80
        except (TypeError, ValueError):
            valid = False
        if valid:
            snapshot["metrics"]["target"] = {"value": selected, "unit": unit or "°C",
                "raw": words[2014], "timestamp": snapshot["timestamp"],
                "quality": "fresh", "source_code": "2014",
                "label": "Aktueller Wassersollwert"}
    if snapshot["metrics"]["target"] and "source_code" not in snapshot["metrics"]["target"]:
        snapshot["metrics"]["target"].update(
            source_code="R02", label="Heizungs-Basissollwert")
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
