"""Application-level LTE operations. Protocol and connection ownership are separate."""

from contextlib import contextmanager
import time

from backend.warmlink_protocol import WarmlinkSession

_last_write = {}


@contextmanager
def open_warmlink(endpoint):
    from backend.bus_connection import manager

    with manager.open(endpoint) as client:
        yield client


def write_control(code, requested, expected):
    from backend.settings import warmlink_endpoint
    from backend.cloud_write import (
        _format_value,
        _number,
        WriteValidationError,
        WriteConflictError,
    )

    endpoint = warmlink_endpoint()
    if endpoint is None:
        raise WriteValidationError("LTE-Anschluss nicht aktiviert")
    desired, _ = _format_value(code, requested)
    register = {"Power": 1011, "Mode": 1012, "H22": 1030, "R02": 1158}[code]
    scale = 10 if code == "R02" else 1
    with open_warmlink(endpoint) as client:
        key = endpoint.connection_key()
        if time.monotonic() - _last_write.get(key, -1000) < 5:
            raise WriteConflictError(
                "Nächster LTE-Schreibvorgang frühestens nach fünf Sekunden"
            )
        previous = _number(client.read_holding(register)[0]) / scale
        if previous != _number(expected):
            raise WriteConflictError("LTE-Wert inzwischen geändert; bitte neu lesen")
        if code == "R02":
            low, high = client.read_holding(1164, 2)
            if not 50 <= low <= high <= 700 or not low <= desired * 10 <= high:
                raise WriteValidationError(
                    "R02 außerhalb der frisch gelesenen LTE-R10/R11-Grenzen"
                )
        if warmlink_endpoint() != endpoint:
            raise WriteConflictError("LTE-Anschluss während der Prüfung geändert")
        if previous == desired:
            return {
                "status": "unchanged",
                "confirmed": True,
                "code": code,
                "value": float(previous),
            }
        try:
            _last_write[key] = time.monotonic()
            client.write_one(register, int(desired * scale))
            time.sleep(0.8)
            actual = _number(client.read_holding(register)[0]) / scale
        except (OSError, ValueError):
            return {
                "status": "unconfirmed",
                "confirmed": False,
                "code": code,
                "message": "LTE-Schreibvorgang nicht bestätigt; Zustand neu lesen, nicht erneut senden",
            }
        return {
            "status": "confirmed" if actual == desired else "unconfirmed",
            "confirmed": actual == desired,
            "code": code,
            "value": float(actual),
            "message": "LTE-Readback ausgewertet",
        }
