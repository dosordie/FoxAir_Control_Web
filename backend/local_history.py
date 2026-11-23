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
ARCHIVE_SCOPE = "local"
DEFROST_REGISTER = 2012
DEFROST_MAX_GAP = 120
DEFROST_STATE = {}
DEFROST_EVENTS = {}


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
            DEFROST_STATE.clear()
            DEFROST_EVENTS.clear()
    return settings()


def record_defrost(row, scope, now):
    try:
        stamp = datetime.fromisoformat(row["timestamp"]).timestamp()
    except (TypeError, ValueError, KeyError):
        return
    if not now - DEFROST_MAX_GAP <= stamp <= now + 10:
        return
    value = row.get("raw")
    if value is None:
        value = row.get("value")
    aliases = {
        "kühlen": 0,
        "heizen": 1,
        "abtauen": 2,
        "sterilisieren": 3,
        "warmwasser": 4,
        "cooling": 0,
        "heating": 1,
        "defrost": 2,
        "hot water": 4,
    }
    value = str(value).strip().casefold()
    mode = int(value) if value in {"0", "1", "2", "3", "4"} else aliases.get(value)
    if mode is None:
        return
    key = (scope, row["transport"])
    active = mode == 2
    last, was_active, started = DEFROST_STATE.get(key, (0, active, None))
    if stamp <= last:
        return
    if not last or stamp - last > DEFROST_MAX_GAP:
        started = None
    elif active and not was_active:
        started = stamp
    elif not active and was_active and started is not None:
        DEFROST_EVENTS[(*key, started)] = stamp
        started = None
    DEFROST_STATE[key] = (stamp, active, started)


def record(rows):
    scope = ARCHIVE_SCOPE
    selected = [(int(key), row) for key, row in rows.items() if int(key) in FIELDS]
    operating = rows.get(str(DEFROST_REGISTER))
    if not selected and not operating:
        return
    now = time.time()
    with LOCK:
        if not config().enabled:
            return
        if operating:
            record_defrost(operating, scope, now)
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
        db.execute("""CREATE TABLE IF NOT EXISTS defrost (
            scope TEXT, transport TEXT, start REAL, finish REAL,
            PRIMARY KEY (scope, transport, start))""")
        db.execute("CREATE INDEX IF NOT EXISTS defrost_expiry ON defrost(finish)")
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
        events = [(*key, end) for key, end in DEFROST_EVENTS.items()]
        for key, state in list(DEFROST_STATE.items()):
            if state[0] < now - DEFROST_MAX_GAP:
                del DEFROST_STATE[key]
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
                db.executemany("INSERT OR IGNORE INTO defrost VALUES (?,?,?,?)", events)
                db.execute("DELETE FROM defrost WHERE finish < ?", (cutoff,))
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
            for key, finish in list(DEFROST_EVENTS.items()):
                if finish < now - 3600:
                    del DEFROST_EVENTS[key]
            return
        DEFROST_EVENTS.clear()
        for row in rows:
            del PENDING[row[:4]]
        old = {sample for sample in SEEN if sample[2] < current - BUCKET}
        SEEN.difference_update(old)


def archive_scopes(db):
    legacy = db.execute(
        """SELECT scope FROM history WHERE scope != ?
        UNION SELECT scope FROM defrost WHERE scope != ? LIMIT 2""",
        (ARCHIVE_SCOPE, ARCHIVE_SCOPE),
    ).fetchall()
    # A single legacy archive belongs to this installation. Keep ambiguous
    # archives separate until an administrator explicitly repairs them.
    return ARCHIVE_SCOPE, legacy[0][0] if len(legacy) == 1 else ARCHIVE_SCOPE


@router.get("/api/history/local/defrost")
def defrost_events(days: int = Query(1, ge=1, le=365)):
    cutoff = time.time() - min(days, config().retention_days) * 86400
    if not (cloud_config.STATE_DIR / "local-history.sqlite").exists():
        return {"events": []}
    with closing(connect()) as db:
        rows = db.execute(
            "SELECT start, finish FROM defrost WHERE scope IN (?, ?) AND finish>=? ORDER BY start DESC",
            (*archive_scopes(db), cutoff),
        ).fetchall()
    return {
        "events": [
            {
                "start": datetime.fromtimestamp(start, timezone.utc).isoformat(),
                "duration_seconds": round(finish - start),
            }
            for start, finish in rows
        ]
    }


@router.get("/api/history/local")
def series(register: int, days: int = Query(1, ge=1, le=365)):
    from fastapi import HTTPException

    if register not in FIELDS:
        raise HTTPException(404, "Messwert nicht verfügbar")
    _, label, unit = FIELDS[register]
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
                FROM history WHERE scope IN (?, ?) AND register=? AND bucket>=?
                GROUP BY bucket / ? ORDER BY bucket / ?""",
                (step, step, *archive_scopes(db), register, cutoff, step, step),
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
