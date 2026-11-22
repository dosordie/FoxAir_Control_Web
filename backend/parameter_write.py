"""Source-defined single parameter edits with preflight and readback.

Timer words use the existing complete-program transaction and enable barriers.
Read-only/service entries never become writable through browser metadata.
"""

import time

from backend.catalog import load_registers
from backend.cloud_write import _number, WriteValidationError, WriteConflictError

SCALES = {
    "TEMP1": 10,
    "TEMP": 10,
    "TEMP05": 2,
    "DIGI5": 10,
    "DIGI6": 1000,
    "DIGI19": 100,
    "DIGI4": 5,
    "POWER_KW_X10": 10,
    "BAR_X10": 10,
    "AMP_X2": 2,
    "AMP_X10": 10,
    "FLOW_M3H_X100": 100,
    "FLOW_M3H_X10": 10,
    "COP_X100": 100,
}
CONTROLS = {1011: "Power", 1012: "Mode", 1030: "H22", 1158: "R02"}
_last_write = {}


def definition(register):
    entry = load_registers().get(str(register), {})
    if entry.get("mode") != "r/w" or not 0 <= register <= 65535:
        raise WriteValidationError("Register ist im Quellkatalog nicht schreibbar")
    return entry


def encode(value, entry):
    kind = str(entry.get("type", "RAW")).upper()
    if kind == "TIME_HHMM" and ":" in str(value):
        try:
            hour, minute = map(int, str(value).split(":"))
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                raise ValueError()
            return hour * 256 + minute
        except ValueError:
            raise WriteValidationError(
                "Uhrzeit als HH:MM zwischen 00:00 und 23:59 eingeben"
            ) from None
    number = _number(value)
    mapping = entry.get("value_map") or {}
    if mapping and number not in {_number(key) for key in mapping}:
        raise WriteValidationError("Wert ist in der Parameterauswahl nicht vorhanden")
    raw = number * SCALES.get(kind, 1)
    signed = (
        bool(entry.get("signed"))
        or kind in SCALES
        or kind
        in (
            "INT16",
            "SIGNED INT16",
            "DIGI1",
            "DIGI9",
            "STEPS_N",
            "MINUTES",
            "SECONDS",
            "DAYS",
            "HZ",
            "RPM",
            "PERCENT",
            "WATT",
            "HOURS",
        )
    )
    minimum, maximum = (-32768, 32767) if signed else (0, 65535)
    if raw != raw.to_integral_value() or not minimum <= raw <= maximum:
        raise WriteValidationError(
            "Wert passt nicht zur Auflösung oder zum 16-Bit-Register"
        )
    if entry.get("write_min") is not None and raw < _number(entry["write_min"]):
        raise WriteValidationError("Wert unterschreitet die Parametergrenze")
    word = int(raw) & 65535
    if kind == "TIME_HHMM" and (word >> 8 > 23 or word & 255 > 59):
        raise WriteValidationError("Ungültige Uhrzeit")
    return word


def cloud_grant(register):
    from backend.cloud_state import catalog

    items = catalog()
    code = next(
        (
            row.get("write_code")
            for row in items
            if row.get("register") == register and row.get("write_code")
        ),
        None,
    )
    return next(
        (row for row in items if row["code"] == code and row.get("write_allowed")), None
    )


def cloud_format(code, value):
    from backend.cloud_state import catalog

    grant = next(
        (row for row in catalog() if row["code"] == code and row.get("write_allowed")),
        None,
    )
    if not grant:
        raise WriteValidationError(
            "Für diesen Parameter ist kein bestätigter Cloud-Schreibcode vorhanden"
        )
    register = grant["register"]
    entry = definition(register)
    encode(value, entry)
    number = _number(value)
    choices = grant.get("write_values") or {}
    if choices and number not in {_number(key) for key in choices}:
        raise WriteValidationError(
            "Cloud-Wert ist für diesen Parameter nicht freigegeben"
        )
    for key, lower in (("write_min", True), ("write_max", False)):
        if grant.get(key) is not None and (
            number < _number(grant[key]) if lower else number > _number(grant[key])
        ):
            raise WriteValidationError(
                "Wert liegt außerhalb der bestätigten Cloud-Parametergrenzen"
            )
    # Ordinary Cloud values use engineering units; packed timers are routed
    # through timers.write and never pass this generic formatter.
    return number, format(number, "f")


def timer_kind(register):
    from backend.timers import SCHEMAS

    return next((kind for kind, schema in SCHEMAS.items() if register in schema), None)


def convert_baseline(register, entry, expected, source, target):
    """Convert an optimistic baseline across transports; server still rereads it."""
    if source is None or source == target:
        return expected
    if source not in ("cloud", "warmlink_raw", "standard_modbus"):
        raise WriteValidationError("Unbekannte Quelle des Ausgangswertes")
    if target != "cloud" and source != "cloud":
        return expected  # Both local transports use raw words.
    from backend import timers

    if source == "cloud":
        return str(
            timers.cloud_word(register, expected)
            if timer_kind(register)
            else encode(expected, entry)
        )
    raw = _number(expected)
    if raw != raw.to_integral_value() or not 0 <= raw <= 65535:
        raise WriteValidationError("Ungültiger Ausgangswert")
    if timer_kind(register):
        return timers.wire_value(register, int(raw))
    kind = str(entry.get("type") or "RAW").upper()
    signed = (
        bool(entry.get("signed"))
        or kind in SCALES
        or kind
        in (
            "INT16",
            "SIGNED INT16",
            "DIGI1",
            "DIGI9",
            "STEPS_N",
            "MINUTES",
            "SECONDS",
            "DAYS",
            "HZ",
            "RPM",
            "PERCENT",
            "WATT",
            "HOURS",
        )
    )
    if signed and not entry.get("value_map") and raw >= 32768:
        raw -= 65536
    return str(raw / SCALES.get(kind, 1))


def write(register, transport, requested, expected, *, expected_transport=None):
    from backend.transport_selection import allows

    if not allows(transport):
        raise WriteValidationError("Andere Verbindung ist global ausgewählt")
    if transport == "display_modbus":
        raise WriteValidationError(
            "Display-Bus ist lesend; nur die separate Snapshot-Spezialfunktion ist freigegeben"
        )
    entry = definition(register)
    expected = convert_baseline(
        register, entry, expected, expected_transport, transport
    )
    word = encode(requested, entry)
    if register == 1234 and not -20 <= _number(requested) <= 20:
        raise WriteValidationError("AT-Steigung muss zwischen -20 und 20 liegen")
    if register == 1235 and not -100 <= _number(requested) <= 100:
        raise WriteValidationError("AT-Offset muss zwischen -100 und 100 °C liegen")
    if register in (1338, 1339, 1340) and not -50 <= _number(requested) <= 25:
        raise WriteValidationError(
            "SG-Temperaturänderung muss zwischen -50 und 25 °C liegen"
        )
    if register == 8801 and transport != "standard_modbus":
        raise WriteValidationError(
            "Virtueller SG-Eingang ist nur am direkten Standard-Modbus bestätigt"
        )
    if (
        entry.get("interface") == "direct_user_modbus"
        and transport != "standard_modbus"
    ):
        raise WriteValidationError(
            "Dieser Parameter benötigt den direkten Standard-Modbus"
        )
    if register in CONTROLS:
        code = CONTROLS[register]
        if transport == "cloud":
            from backend.cloud_write import write_control

            return write_control(code, requested, expected)
        if transport == "warmlink_raw":
            from backend.warmlink import write_control

            # Old control API compares engineering values; parameter API's
            # local baseline is explicitly a raw Modbus word.
            baseline = _number(expected) / (10 if register == 1158 else 1)
            return write_control(code, requested, baseline)
    kind = timer_kind(register)
    if kind:
        from backend import timers

        snapshot = timers.read(kind, transport)["values"]
        baseline = (
            timers.cloud_word(register, expected)
            if transport == "cloud"
            else int(_number(expected))
        )
        if snapshot[str(register)] != baseline:
            raise WriteConflictError("Timerwert inzwischen geändert; neu lesen")
        desired = {**snapshot, str(register): word}
        return timers.write(kind, transport, desired, snapshot)
    if transport == "cloud":
        from backend.cloud_write import write_control

        grant = cloud_grant(register)
        if not grant:
            raise WriteValidationError(
                "Kein bestätigter Cloud-Schreibcode; Modbus verwenden"
            )
        return write_control(grant["code"], requested, expected)
    if transport not in ("warmlink_raw", "standard_modbus"):
        raise WriteValidationError("Verbindung unterstützt keine Schreibzugriffe")
    from backend.settings import warmlink_endpoint, standard_endpoint
    from backend.warmlink import open_warmlink
    from backend.rtu import open_rtu
    from backend.last_values import remember_words
    from backend.diagnostics import log_event

    provider = warmlink_endpoint if transport == "warmlink_raw" else standard_endpoint
    endpoint = provider()
    if endpoint is None:
        raise WriteValidationError("Modbus-Anschluss nicht eingerichtet")
    with (
        open_warmlink(endpoint) if transport == "warmlink_raw" else open_rtu(endpoint)
    ) as client:
        if time.monotonic() - _last_write.get(endpoint, -1000) < 5:
            raise WriteConflictError(
                "Nächster Schreibauftrag frühestens nach fünf Sekunden"
            )
        previous = client.read_holding(register, 1)[0]
        if _number(expected) != previous:
            raise WriteConflictError("Parameter inzwischen geändert; neu lesen")
        if register == 8801:
            mode = client.read_holding(1334, 1)[0]
            if mode not in (3, 7) or word not in range(1, 4 if mode == 7 else 5):
                raise WriteValidationError(
                    "SG-Eingang passt nicht zur aktuellen SG01-Konfiguration"
                )
        curve_point = register in (1250, 1251, 1252, 1253, 1254, 1255)
        if register == 1235 and previous != word:
            curve_point = client.read_holding(1236, 1)[0] == 2
        if curve_point and previous != word:
            low, high = client.read_holding(1164, 2)
            if not 50 <= low <= high <= 700 or not low <= word <= high:
                raise WriteValidationError(
                    "AT-Kurvenpunkt außerhalb der aktuellen R10/R11-Grenzen"
                )
        if register in (1157, 1158, 1159):
            first = {1157: 1176, 1158: 1164, 1159: 1162}[register]
            low, high = client.read_holding(first, 2)
            if not 50 <= low <= high <= 700 or not low <= word <= high:
                raise WriteValidationError(
                    "Sollwert außerhalb der aktuellen Parametergrenzen"
                )
        if provider() != endpoint:
            raise WriteConflictError("Anschluss während der Prüfung geändert")
        if previous == word:
            return {"status": "unchanged", "confirmed": True}
        _last_write[endpoint] = time.monotonic()
        try:
            client.write_one(register, word)
            time.sleep(0.8)
            actual = client.read_holding(register, 1)[0]
            if provider() != endpoint:
                raise ValueError("Anschluss gewechselt")
            remember_words(endpoint, register, [actual], transport=transport)
        except (OSError, ValueError):
            log_event(
                "write-error",
                f"Parameterregister {register}: Antwort unklar; keine Wiederholung",
            )
            return {
                "status": "unconfirmed",
                "confirmed": False,
                "message": "Antwort unklar. Zustand neu lesen; Auftrag nicht erneut senden.",
            }
        confirmed = actual == word
        log_event(
            "write",
            f"Parameterregister {register}: Readback {'bestätigt' if confirmed else 'abweichend'}",
        )
        return {
            "status": "confirmed" if confirmed else "unconfirmed",
            "confirmed": confirmed,
        }
