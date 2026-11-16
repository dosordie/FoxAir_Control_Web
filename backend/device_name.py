"""Persist only the selected Cloud device's display name, bound to its account."""
import hashlib
import os
from pathlib import Path
import threading
import time

from backend.cloud_config import credentials, _read_json, _atomic_json

NAME_FILE = Path(os.environ.get("FOXAIR_STATE_DIR", "/var/lib/foxair-web")) / "device-name.json"
_lock = threading.RLock()
_checked: dict[str, float] = {}


def identity():
    return hashlib.sha256("\0".join(credentials()).encode()).hexdigest()


def get_name():
    record = _read_json(NAME_FILE)
    name = record.get("name")
    return name if record.get("account") == identity() and isinstance(name, str) and name else "FoxAir"


def remember_name(row, account):
    if not isinstance(row, dict) or credentials() != account:
        return
    name = next((row[key].strip()[:160] for key in ("deviceNickName", "deviceName")
                 if isinstance(row.get(key), str) and row[key].strip()), "")
    if name:
        with _lock:
            record = {"account": identity(), "name": name}
            if _read_json(NAME_FILE) != record:
                try:
                    _atomic_json(NAME_FILE, record)
                except OSError:
                    pass


def refresh_name(client):
    # No extra device-list request on every live refresh, including on failure.
    if not all(credentials()):
        return
    with _lock:
        key = identity()
        if time.monotonic() - _checked.get(key, -1000) < 900:
            return
        _checked.clear()
        _checked[key] = time.monotonic()
    account = credentials()
    def fetch():
        from backend.cloud_read import _cloud_lock
        try:
            with _cloud_lock:
                if credentials() != account:
                    return
                rows = client.devices()
                if isinstance(rows, list):
                    row = next((r for r in rows if isinstance(r, dict) and r.get("deviceCode") == account[2]), {})
                    remember_name(row, account)
        except RuntimeError:
            pass  # Names are optional; dashboard measurements remain usable.
    threading.Thread(target=fetch, daemon=True, name="cloud-device-name").start()
