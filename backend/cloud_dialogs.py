"""Source-backed special dialog definitions and targeted Cloud refresh.

Timer editing uses backend.timers; operating switches use cloud_write.
SG, AT and fault entries remain read-only.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any

from backend.cloud_state import catalog, cached_raw_values, merge, log_event
from backend.cloud_read import CloudError, UnsupportedCloudCode, _cloud_lock, _reader

_BASE_DIALOGS = (
    ("wp", "Wärmepumpe", "Ein/Aus, Modus, Wasser- und Heizsollwerte",
     ("Power", "Mode", "ModeState", "R01", "R02", "R03", "2014",
      "T01", "T02", "T04", "T08", "T39", "H36")),
    ("at", "AT-Kurve", "Lineare und 7-Punkt-Außentemperaturkompensation",
     ("H36", "compensate_slope", "compensate_offset",
      "CP1-1", "CP1-2", "CP1-3", "CP1-5", "CP1-6", "CP1-7",
      "T04", "2014", "R10", "R11")),
    ("sg", "SG-Ready", "SG01–SG08 und aktuell gemeldeter SG-Status",
     ("SG01", "SG02", "SG03", "SG04", "SG05", "SG06", "SG07", "SG08",
      "SG Status")),
    ("silent", "Ruhemodus", "Stille-/Silent-Timer und Freigaben",
     ("Timer_Mute_On_En", "TimerMuteOnHour", "TimerMuteOnMinute",
      "Timer_Mute_Off_En", "TimerMuteOffHour", "TimerMuteOffMinute")),
    ("timer", "Zeitprogramme", "Ein/Aus-Wochentimer und Betriebsarten-Timer M1–M6",
     tuple(f"KG{v}" for v in range(1, 13)) + ("KG13~KG28", "KG29~KG44", "KG45~KG60") +
     tuple(f"M{n} {suffix}" for n in range(1, 7)
           for suffix in ("Start", "End", "Mode", "Heating Target",
                          "Cooling Target", "Hot Water Target", "Max. Power")) +
     ("M1_2 Enalbe", "M3_4 Enalbe", "M5_6 Enalbe")),
    ("fault", "Störungsübersicht", "Status- und Fehlerwörter, keine Fehlerfreiheit bei fehlenden Werten",
     ("O01~023",) + tuple(f"Fault{i}" for i in range(1, 11))),
)

_dialog_lock = threading.Lock()
_last_read: dict[str, float] = {}
READ_INTERVAL = 20.0
# Local register addresses are sourced from the pinned FoxAir Control catalog.
_LOCAL_REGISTERS = {
    "wp": (1011, 1012, 2012, 1157, 1158, 1159, 2014, 2045, 2046, 2048, 2047, 2077, 1236),
    "at": (1236, 1234, 1235, 1250, 1251, 1252, 1253, 1254, 1255, 1164, 1165, 2048, 2014),
    "sg": (*range(1334, 1342), 2034, 2133),
    "fault": tuple(range(2081, 2091)),
}


def definitions() -> list[dict[str, Any]]:
    known = {r["code"]: r for r in catalog()}
    result: list[dict[str, Any]] = []
    for slug, name, description, candidate_codes in _BASE_DIALOGS:
        rows = [known[code] for code in candidate_codes if code in known]
        from backend.register_definitions import AT_CURVE_POINTS
        result.append({
            "curve_points": [{"outdoor":at,"register":register} for at,register in AT_CURVE_POINTS] if slug == "at" else [],
            "id": slug, "title": name, "description": description,
            "codes": [row["code"] for row in rows],
            "read_only": slug == "fault", "count": len(rows),
            "local_registers": list(_LOCAL_REGISTERS.get(slug, ())),
            "registers": list(dict.fromkeys(row["register"] for row in rows if isinstance(row.get("register"),int) and row["register"] <= 65535 and (row.get("confidence") == "confirmed" or row.get("write_allowed")))),
        })
    return result


def refresh(slug: str) -> dict[str, Any]:
    dialog = next((row for row in definitions() if row["id"] == slug), None)
    if not dialog:
        raise ValueError("Unbekannter Spezialdialog")
    with _dialog_lock:
        now = time.monotonic()
        if now - _last_read.get(slug, -READ_INTERVAL) < READ_INTERVAL:
            return {"updated": False, "reason": "rate_limit", "count": 0}
        _last_read[slug] = now
    confirmed = set(cached_raw_values())
    # Unknown candidates may be unsupported and trigger expensive bisection.
    # Limit exploratory requests to 12; the first background full scan already
    # verifies support for all catalog candidates.
    probe = [code for code in dialog["codes"] if code not in confirmed][:12]
    wanted = [code for code in dialog["codes"] if code in confirmed] + probe
    if not wanted:
        return {"updated": False, "reason": "no_codes", "count": 0}
    values: dict[str, dict[str, Any]] = {}
    failures = 0

    def read_batch(codes: list[str], depth: int = 0) -> None:
        nonlocal failures
        if not codes:
            return
        try:
            response = _reader().read_codes(codes)
        except UnsupportedCloudCode:
            if len(codes) > 1 and depth < 6:
                half = len(codes) // 2
                read_batch(codes[:half], depth + 1)
                read_batch(codes[half:], depth + 1)
                return
            failures += len(codes)
            return
        values.update(response)

    try:
        with _cloud_lock:
            for offset in range(0, len(wanted), 50):
                read_batch(wanted[offset:offset+50])
    except CloudError:
        log_event("error", "Spezialdialog-Cloud-Leseabfrage fehlgeschlagen")
        raise
    merge(values)
    log_event("read", "Spezialdialog-Cloudwerte aktualisiert", count=len(values))
    return {"updated": True, "count": len(values), "unsupported": failures}
