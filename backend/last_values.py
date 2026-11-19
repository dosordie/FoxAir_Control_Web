"""Private persistent last-known engineering values, shared by all transports.

This store never authorizes writes and never changes a measurement timestamp.
Configuration identity separates installations; transport selection does not.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import sqlite3
import threading

from backend.cloud_config import STATE_DIR


def installation_key():
    from backend.cloud_config import credentials
    from backend.settings import warmlink_config, standard_endpoint

    username, _password, device = credentials()
    lte = warmlink_config()
    standard = standard_endpoint()
    identity = [
        username,
        device,
        lte["host"],
        lte["port"],
        (standard.host, standard.port, standard.slave) if standard else None,
    ]
    from backend.settings import local_bus_config

    display = local_bus_config("display_modbus")
    if display["host"]:
        identity.append(("display", display["host"], display["port"]))
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


class LastValues:
    def __init__(self, path, identity=installation_key):
        self.path = path
        self.identity = identity
        self.lock = threading.RLock()

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.path, timeout=2)
        self.path.chmod(0o600)
        db.execute(
            "CREATE TABLE IF NOT EXISTS last_values (scope TEXT, register INTEGER, stamp TEXT, value TEXT, PRIMARY KEY(scope,register))"
        )
        try:
            with db:
                yield db
        finally:
            db.close()

    def remember(self, rows, *, scope=None):
        scope = scope or self.identity()
        records = []
        for key, row in rows.items():
            if (
                row.get("value") is None
                or not row.get("timestamp")
                or (
                    isinstance(row.get("value"), float)
                    and not math.isfinite(row["value"])
                )
            ):
                continue
            records.append(
                (
                    scope,
                    int(key),
                    row["timestamp"],
                    json.dumps(row, ensure_ascii=False, allow_nan=False),
                )
            )
        if not records:
            return
        try:
            with self.lock, self._connect() as db:
                db.executemany(
                    "INSERT INTO last_values VALUES (?,?,?,?) ON CONFLICT(scope,register) DO UPDATE SET stamp=excluded.stamp,value=excluded.value WHERE excluded.stamp >= last_values.stamp",
                    records,
                )
        except (OSError, sqlite3.Error):
            pass  # Telemetry remains usable with a full or read-only disk.

    def values(self):
        try:
            with self.lock, self._connect() as db:
                rows = db.execute(
                    "SELECT register,value FROM last_values WHERE scope=?",
                    (self.identity(),),
                ).fetchall()
            now = datetime.now(timezone.utc)
            result = {}
            for register, payload in rows:
                row = json.loads(payload)
                age = (now - datetime.fromisoformat(row["timestamp"])).total_seconds()
                result[str(register)] = {
                    **row,
                    "quality": "stale" if age > 300 else "cached",
                }
            return result
        except (OSError, sqlite3.Error, ValueError, TypeError):
            return {}


store = LastValues(STATE_DIR / "last-register-values.sqlite")


def remember_words(endpoint, start, words, *, transport="warmlink_raw", timestamp=None):
    from backend.catalog import format_raw, load_registers
    from backend.register_cache import is_public_register
    from backend.settings import warmlink_endpoint, standard_endpoint, display_endpoint

    selected = (
        warmlink_endpoint()
        if transport == "warmlink_raw"
        else display_endpoint()
        if transport == "display_modbus"
        else standard_endpoint()
    )
    if selected != endpoint:
        return
    scope = installation_key()
    stamp = (
        datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        if timestamp is not None
        else datetime.now(timezone.utc).isoformat()
    )
    rows = {}
    for offset, raw in enumerate(words):
        register = start + offset
        if not is_public_register(register):
            continue
        entry = load_registers()[str(register)]
        value, unit = format_raw(raw, entry)
        rows[str(register)] = {
            "register": register,
            "raw": raw,
            "value": value,
            "unit": unit,
            "transport": transport,
            "timestamp": stamp,
        }
    store.remember(rows, scope=scope)


def remember_cloud(rows, account):
    from backend.cloud_config import credentials
    from backend.cloud_state import catalog, display_label

    if credentials() != account:
        return
    scope = installation_key()
    from backend.timers import SCHEMAS

    timer_codes = {
        code: register
        for schema in SCHEMAS.values()
        for register, code in schema.items()
    }
    mappings = {
        item["code"]: item
        for item in catalog()
        if (
            item.get("confidence") == "confirmed"
            or timer_codes.get(item["code"]) == item.get("register")
        )
        and isinstance(item.get("register"), int)
    }
    values = {}
    for code, row in rows.items():
        mapping = mappings.get(code)
        if not mapping or row.get("value") is None:
            continue
        register = mapping["register"]
        label = display_label(register, row["value"])
        values[str(register)] = {
            **row,
            "register": register,
            "raw": None,
            "unit": ""
            if label is not None
            else row.get("unit") or mapping.get("unit") or "",
            "transport": "cloud",
            "code": code,
            "display_value": label,
        }
    store.remember(values, scope=scope)


def fill_dashboard(snapshot):
    from backend.register_definitions import DASHBOARD_FIELDS

    values = store.values()
    for name, register in DASHBOARD_FIELDS.items():
        last = values.get(str(register))
        current = snapshot["metrics"].get(name)
        if last and (
            current is None
            or (
                current.get("quality") in ("cached", "stale")
                and last["timestamp"] > current["timestamp"]
            )
        ):
            snapshot["metrics"][name] = last
    selected = values.get("2014")
    target = snapshot["metrics"].get("target")
    if (
        selected
        and isinstance(selected.get("value"), (int, float))
        and 5 <= selected["value"] <= 80
    ):
        if not target or (
            target.get("quality") in ("cached", "stale")
            and selected["timestamp"] >= target["timestamp"]
        ):
            snapshot["metrics"]["target"] = {
                **selected,
                "source_code": "2014",
                "label": "Aktueller Wassersollwert",
            }
    return snapshot
