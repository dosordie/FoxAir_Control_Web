"""Optional local measurement history in RAM and batched SQLite storage."""

from contextlib import closing
from datetime import datetime, timezone
import logging
import math
import sqlite3
from threading import Lock
import time

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from backend import cloud_config

router = APIRouter()
LOCK = Lock()
BUCKET = 300
FLUSH_SECONDS = 900
FIELDS = {
    2048: ("outdoor", "Außen", "°C"),
    2045: ("return", "Eintritt", "°C"),
    2046: ("supply", "Austritt", "°C"),
    2014: ("target", "Wirksamer Heiz-Sollwert", "°C"),
    2072: ("frequency", "Verdichterfrequenz", "Hz"),
    2054: ("electrical", "Elektrische Leistung", "kW"),
    2059: ("thermal", "Thermische Leistung", "kW"),
    2060: ("cop", "COP", ""),
}
PENDING = {}
SEEN = set()


class Settings(BaseModel):
    enabled: bool = False
    retention_days: int = Field(default=90, ge=1, le=365)


def config_path():
    return cloud_config.STATE_DIR / "local-history.json"


def config():
    return Settings.model_validate(cloud_config._read_json(config_path()))


@router.get("/api/history/local/settings")
def settings():
    return {
        **config().model_dump(),
        "fields": [
            {"register": register, "label": label, "unit": unit}
            for register, (_, label, unit) in FIELDS.items()
        ],
    }


@router.post("/api/history/local/settings")
def save(payload: Settings, request: Request):
    cloud_config.require_admin(request)
    with LOCK:
        cloud_config._atomic_json(config_path(), payload.model_dump())
        if not payload.enabled:
            PENDING.clear()
            SEEN.clear()
    return settings()


def record(rows, scope):
    selected = [(int(key), row) for key, row in rows.items() if int(key) in FIELDS]
    if not selected:
        return
    now = time.time()
    with LOCK:
        if not config().enabled:
            return
        for register, row in selected:
            value = row.get("value")
            if isinstance(value, str):
                try:
                    value = float(value.replace(",", "."))
                except ValueError:
                    continue
            if type(value) not in (int, float) or not math.isfinite(value):
                continue
            if register == 2014 and not 5 <= value <= 80:
                continue
            try:
                stamp = datetime.fromisoformat(row["timestamp"]).timestamp()
            except (TypeError, ValueError, KeyError):
                continue
            if not now - BUCKET <= stamp <= now + 10:
                continue
            bucket = int(stamp // BUCKET) * BUCKET
            key = (scope, register, bucket, row["transport"])
            sample = (*key, stamp, value)
            if sample in SEEN or len(SEEN) >= 100000:
                continue
            SEEN.add(sample)
            count, total, low, high = PENDING.get(key, (0, 0.0, value, value))
            PENDING[key] = (count + 1, total + value, min(low, value), max(high, value))


def connect():
    path = cloud_config.STATE_DIR / "local-history.sqlite"
    db = sqlite3.connect(path, timeout=3)
    try:
        path.chmod(0o600)
        db.execute("""CREATE TABLE IF NOT EXISTS history (
        scope TEXT, register INTEGER, bucket INTEGER, transport TEXT,
        count INTEGER, total REAL, low REAL, high REAL,
        PRIMARY KEY (scope, register, bucket, transport))""")
        db.execute("CREATE INDEX IF NOT EXISTS history_expiry ON history(bucket)")
    except BaseException:
        db.close()
        raise
    return db


def flush(*, final=False):
    with LOCK:
        cfg = config()
        if (
            not cfg.enabled
            and not (cloud_config.STATE_DIR / "local-history.sqlite").exists()
        ):
            return
        now = time.time()
        current = int(now // BUCKET) * BUCKET
        cutoff = now - cfg.retention_days * 86400
        rows = [
            (*key, *value)
            for key, value in PENDING.items()
            if final or key[2] < current
        ]
        try:
            with closing(connect()) as db, db:
                db.executemany(
                    """INSERT INTO history VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(scope, register, bucket, transport) DO UPDATE SET
                    count=history.count+excluded.count, total=history.total+excluded.total,
                    low=min(history.low,excluded.low), high=max(history.high,excluded.high)""",
                    rows,
                )
                db.execute("DELETE FROM history WHERE bucket < ?", (cutoff,))
        except (OSError, sqlite3.Error):
            logging.getLogger(__name__).warning(
                "Lokaler Verlauf konnte nicht gespeichert werden"
            )
            for key in list(PENDING):
                if key[2] < now - 3600:
                    del PENDING[key]
            SEEN.difference_update(
                {sample for sample in SEEN if sample[2] < current - BUCKET}
            )
            return
        for row in rows:
            del PENDING[row[:4]]
        old = {sample for sample in SEEN if sample[2] < current - BUCKET}
        SEEN.difference_update(old)


@router.get("/api/history/local")
def series(register: int, days: int = Query(1, ge=1, le=365)):
    from backend.last_values import installation_key
    from fastapi import HTTPException

    if register not in FIELDS:
        raise HTTPException(404, "Messwert nicht verfügbar")
    _, label, unit = FIELDS[register]
    scope = installation_key()
    now = time.time()
    # Downsample long views to keep the browser responsive.
    step = BUCKET if days <= 2 else 1800 if days <= 30 else 7200
    period = min(days, config().retention_days)
    cutoff = int((now - period * 86400) // step) * step
    points = []
    if (cloud_config.STATE_DIR / "local-history.sqlite").exists():
        with closing(connect()) as db:
            rows = db.execute(
                """SELECT (bucket / ?) * ?, sum(total)/sum(count),
                min(low), max(high), group_concat(DISTINCT transport)
                FROM history WHERE scope=? AND register=? AND bucket>=?
                GROUP BY bucket / ? ORDER BY bucket / ?""",
                (step, step, scope, register, cutoff, step, step),
            ).fetchall()
        points = [
            {
                "time": datetime.fromtimestamp(bucket, timezone.utc).isoformat(),
                "value": value,
                "min": low,
                "max": high,
                "source": source,
            }
            for bucket, value, low, high, source in rows
        ]
    return {"label": label, "unit": unit, "points": points, "step_seconds": step}
