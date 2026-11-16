"""Process-local Cloud scan/cache and redacted operational events.

The whole FoxAir_Control discovery catalog is bundled as a CI-generated
read-only JSON snapshot. Full scan is done asynchronously once per account
and only refreshed on demand. Subsequent live reads only query supported,
confirmed live codes, as in FoxAir_Control's RE documentation.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any

from backend.cloud_config import credentials
from backend.cloud_read import CloudError, UnsupportedCloudCode, _reader, _cloud_lock

_LOCK = threading.RLock()
_ROWS: dict[str, dict[str, Any]] = {}
_LOGS: deque[dict[str, Any]] = deque(maxlen=150)
_SOURCE: tuple[str, str, str] | None = None
_STATUS = "idle"
_PROGRESS = 0
_LAST_SCAN = 0.0
_LAST_ERROR: str | None = None
_CATALOG_CACHE: list[dict[str, Any]] | None = None
_CACHE_FILE = Path(os.environ.get("FOXAIR_STATE_DIR", "/var/lib/foxair-web")) / "cloud-last-values.json"
_LAST_SAVED = 0.0
STALE_AFTER_SECONDS = 300  # five minutes; timeout never changes live availability



def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(kind: str, message: str, *, count: int | None = None) -> None:
    # All messages MUST be hardcoded or counts from the application, never
    # cloud responses, usernames, tokens, IPs or device identifiers.
    event: dict[str, Any] = {"time": _ts(), "kind": kind, "message": message}
    if count is not None:
        event["count"] = count
    with _LOCK:
        _LOGS.appendleft(event)


def logs() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_LOGS)


def catalog() -> list[dict[str, Any]]:
    global _CATALOG_CACHE
    with _LOCK:
        if _CATALOG_CACHE is not None:
            return _CATALOG_CACHE
    path = Path(__file__).resolve().parents[1] / "frontend" / "dist" / "cloud_catalog.json"
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
        items = source.get("items")
        if not isinstance(items, list) or len(items) < 400:
            raise ValueError("incomplete catalog")
        rows = [r for r in items if isinstance(r, dict) and isinstance(r.get("code"), str)]
    except (OSError, ValueError, TypeError):
        rows = []
    with _LOCK:
        if rows:
            _CATALOG_CACHE = rows
    return rows


def _account() -> tuple[str, str, str]:
    return credentials()


def _identity(account: tuple[str, str, str]) -> str:
    # Hash an entire account identity; no plaintext account identifiers in cache.
    return hashlib.sha256("\\0".join(account).encode("utf-8")).hexdigest()


def _load_cache(account: tuple[str, str, str]) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        if payload.get("account") != _identity(account):
            return {}
        rows = payload.get("rows", {})
        if not isinstance(rows, dict):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for code, data in list(rows.items())[:850]:
            if (not isinstance(code, str) or not isinstance(data, dict)
                    or not isinstance(data.get("timestamp"), str)):
                continue
            value = data.get("value")
            if value is None or isinstance(value, (str, int, float, bool)):
                result[code] = {
                    "value": value, "unit": str(data.get("unit") or "")[:24],
                    "timestamp": data["timestamp"], "quality": "cached", "supported": True,
                }
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _save_cache(account: tuple[str, str, str], rows: dict[str, dict[str, Any]]) -> None:
    # No cloud password, deviceCode, tokens or raw responses on disk.
    # Atomically replace a *single* private snapshot, limited to 850 scalar rows.
    values = {}
    for code, row in list(rows.items())[:850]:
        value = row.get("value")
        if not isinstance(value, (str, int, float, bool)):
            continue
        values[code] = {"value": value, "unit": row.get("unit") or "",
                        "timestamp": row.get("timestamp")}
    payload = {"version": 1, "account": _identity(account), "rows": values}
    fd = -1
    filename = ""
    try:
        _CACHE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix=".cloud-values-", dir=_CACHE_FILE.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(payload, handle, ensure_ascii=False)
        os.chmod(filename, 0o600)
        os.replace(filename, _CACHE_FILE)
    except OSError:
        # Read-only systemd service or disk-full must not break live telemetry.
        pass
    finally:
        if fd >= 0:
            os.close(fd)
        if filename and os.path.exists(filename):
            os.unlink(filename)


def _reset_if_changed() -> tuple[str, str, str]:
    global _SOURCE, _STATUS, _PROGRESS, _LAST_SCAN, _LAST_ERROR, _LAST_SAVED
    account = _account()
    with _LOCK:
        if _SOURCE != account:
            _SOURCE = account
            _ROWS.clear()
            _ROWS.update(_load_cache(account))
            _LAST_SAVED = 0.0
            _STATUS = "idle"
            _PROGRESS = 0
            _LAST_SCAN = 0
            _LAST_ERROR = None
    return account


def merge(rows: dict[str, dict[str, Any]], *, source: tuple[str, str, str] | None = None) -> None:
    global _LAST_SAVED
    account = _reset_if_changed()
    if source is not None and source != account:
        return
    stamp = _ts()
    with _LOCK:
        for code, item in rows.items():
            if "value" not in item:
                continue
            _ROWS[code] = {**item, "timestamp": stamp, "quality": "fresh", "supported": True}
        if rows and (not _LAST_SAVED or time.monotonic() - _LAST_SAVED >= 60):
            _save_cache(account, _ROWS)
            _LAST_SAVED = time.monotonic()


def cached_raw_values() -> dict[str, dict[str, Any]]:
    """Last good cloud values including original timestamps, never marked fresh."""
    _reset_if_changed()
    with _LOCK:
        result = dict(_ROWS)
    now = datetime.now(timezone.utc)
    output: dict[str, dict[str, Any]] = {}
    for code, row in result.items():
        if not isinstance(row.get("timestamp"), str):
            continue
        if not isinstance(row.get("value"), (str, int, float, bool)):
            continue
        try:
            age = (now - datetime.fromisoformat(row["timestamp"])).total_seconds()
        except (ValueError, TypeError):
            continue
        output[code] = {**row, "quality": "stale" if age > STALE_AFTER_SECONDS else "cached"}
    return output


def value_rows() -> dict[str, Any]:
    _reset_if_changed()
    items = catalog()
    with _LOCK:
        states = dict(_ROWS)
        status = _STATUS
        progress = _PROGRESS
        last_scan = _LAST_SCAN
        err = _LAST_ERROR
    values: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for row in sorted(items, key=lambda r:
                      (r.get("register") if isinstance(r.get("register"), int) else 999999,
                       r["code"])):
        current = states.get(row["code"])
        quality = current.get("quality", "unknown") if current else "unknown"
        if current and current.get("timestamp"):
            try:
                age = (now - datetime.fromisoformat(current["timestamp"])).total_seconds()
                if age > (STALE_AFTER_SECONDS if row.get("kind") == "live" else 86400):
                    quality = "stale"
            except (ValueError, TypeError):
                quality = "unknown"
        label = display_label(row.get("register"), current.get("value") if current else None)
        values.append({
            "code": row["code"],
            "name": row.get("name") or row["code"],
            "register": row.get("register"),
            "group": row.get("group") or "CLOUD",
            "kind": row.get("kind") or "other",
            "unit": "" if label is not None else
                    ((current or {}).get("unit") or row.get("unit") or ""),
            "confidence": row.get("confidence") or "",
            "value": current.get("value") if current else None,
            "display_value": label,
            "timestamp": current.get("timestamp") if current else None,
            "quality": quality,
            "supported": current is not None,
        })
    return {
        "items": values, "total": len(values),
        "supported": len(states), "status": status,
        "progress": progress, "last_scan": last_scan, "error": err,
    }


def display_label(register: int | None, raw: Any) -> str | None:
    """Use reviewed MAIN register enums; never guess an unknown code's meaning."""
    from backend.catalog import load_registers
    if register is None or raw is None:
        return None
    entry = load_registers().get(str(register), {})
    choices = entry.get("value_map")
    if not isinstance(choices, dict):
        return None
    value = str(raw).strip()
    try:
        number = float(value)
        if number.is_integer():
            value = str(int(number))
    except (ValueError, OverflowError):
        pass
    label = choices.get(value)
    return str(label) if label is not None else None


def live_codes() -> list[str]:
    _reset_if_changed()
    with _LOCK:
        present = set(_ROWS)
    return [row["code"] for row in catalog()
            if row.get("kind") == "live" and row["code"] in present]


def scan_start(*, force: bool = False) -> dict[str, Any]:
    global _STATUS, _PROGRESS, _LAST_ERROR
    account = _reset_if_changed()
    if not all(account):
        raise CloudError("Cloud ist nicht vollständig konfiguriert")
    codes = catalog()
    if not codes:
        raise CloudError("Cloud-Code-Katalog fehlt im Web-Build")
    with _LOCK:
        if _STATUS == "running":
            return {"started": False, "reason": "running"}
        if not force and _LAST_SCAN and time.monotonic() - _LAST_SCAN < 600:
            return {"started": False, "reason": "recent"}
        _STATUS = "running"
        _PROGRESS = 0
        _LAST_ERROR = None
    log_event("scan", "Vollständiger Cloud-Katalogscan gestartet", count=len(codes))
    t = threading.Thread(target=_scan_worker, args=(account, codes), daemon=True, name="foxair-cloud-scan")
    t.start()
    return {"started": True, "count": len(codes)}


def _scan_worker(account: tuple[str, str, str], entries: list[dict[str, Any]]) -> None:
    global _STATUS, _PROGRESS, _LAST_SCAN, _LAST_ERROR
    succeeded = 0
    completed = 0
    unsupported = 0
    errors = 0
    def fetch(codes: list[str], depth: int = 0) -> None:
        nonlocal succeeded, completed, unsupported, errors
        if _account() != account:
            raise CloudError("Cloud-Konto gewechselt, Scan abgebrochen")
        # A failed unsupported code must not invalidate the other codes.
        try:
            with _cloud_lock:
                result = _reader().read_codes(codes)
        except UnsupportedCloudCode:
            if len(codes) > 1 and depth < 7:
                m = len(codes) // 2
                fetch(codes[:m], depth + 1)
                fetch(codes[m:], depth + 1)
                return
            unsupported += len(codes)
            completed += len(codes)
            return
        except CloudError:
            errors += 1
            raise
        merge(result, source=account)
        succeeded += len(result)
        completed += len(codes)
        unsupported += len(codes) - len(result)

    try:
        for start in range(0, len(entries), 50):
            batch = [x["code"] for x in entries[start:start + 50]]
            fetch(batch)
            with _LOCK:
                _PROGRESS = completed
        with _LOCK:
            if _SOURCE == account:
                _STATUS = "complete"
                _LAST_SCAN = time.monotonic()
        log_event("scan", "Cloud-Katalogscan beendet", count=succeeded)
        if unsupported:
            log_event("info", "Codes ohne gültigen Cloudwert", count=unsupported)
    except CloudError:
        with _LOCK:
            if _SOURCE == account:
                _STATUS = "error"
                _LAST_ERROR = "Cloud-Katalogscan abgebrochen; bisherige Werte bleiben erhalten"
        log_event("error", "Cloud-Katalogscan abgebrochen; bitte Verbindung prüfen")
    except Exception:
        # Never surface response body, secrets or exception traceback in logs.
        with _LOCK:
            if _SOURCE == account:
                _STATUS = "error"
                _LAST_ERROR = "Unerwarteter Scanfehler"
        log_event("error", "Unerwarteter Cloud-Katalogscanfehler")
