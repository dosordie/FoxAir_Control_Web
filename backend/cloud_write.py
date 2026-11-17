"""Source-granted PHNIX controls with preflight, limits and readback.

Exactly one control attempt; transport failures never replay a mutation.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import threading
import time
from typing import Any

from backend.cloud_config import credentials
from backend.cloud_read import CloudError, _reader, _cloud_lock
from backend.cloud_state import merge, log_event

MIN_WRITE_GAP = 5.0
_LAST_WRITE = 0.0


class WriteValidationError(ValueError):
    pass


class WriteConflictError(ValueError):
    pass


def _number(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise WriteValidationError("Boolescher Wert nicht zulässig")
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, TypeError):
        raise WriteValidationError("Ungültiger Zahlenwert") from None
    if not result.is_finite():
        raise WriteValidationError("Endlicher Zahlenwert erforderlich")
    return result


def _format_value(code: str, requested: Any) -> tuple[Decimal, str]:
    number = _number(requested)
    if code in ("Power", "H22"):
        if number not in (0, 1):
            raise WriteValidationError("Nur Ein (1) oder Aus (0) zulässig")
        return number, str(int(number))
    if code == "Mode":
        if number != number.to_integral_value() or not 0 <= number <= 4:
            raise WriteValidationError("Mode: nur 0–4 nach bestätigtem Katalog")
        return number, str(int(number))
    if code == "R02":
        if number * 10 != (number * 10).to_integral_value():
            raise WriteValidationError("R02: Auflösung 0,1 °C")
        if not Decimal("5") <= number <= Decimal("70"):
            raise WriteValidationError("R02: Wert außerhalb des allgemeinen sicheren Bereichs")
        return number, format(number, "f")
    from backend.parameter_write import cloud_format
    return cloud_format(code, requested)


def _limit(row: dict[str, Any] | None, name: str) -> Decimal:
    if not row:
        raise WriteValidationError(f"{name} ist nicht lesbar; keine Sollwertänderung")
    limit = _number(row.get("value"))
    if not Decimal("5") <= limit <= Decimal("70"):
        raise WriteValidationError(f"{name} liefert keinen plausiblen Wert")
    return limit


def write_control(code: str, requested: Any, expected: Any) -> dict[str, Any]:
    global _LAST_WRITE
    # Legacy controls or grants exported from the pinned desktop source only.
    desired, wire_value = _format_value(code, requested)
    expected_value = _number(expected)
    account = credentials()
    if not all(account):
        raise CloudError("Cloud-Konto nicht vollständig eingerichtet")

    with _cloud_lock:
        # The lock covers preflight, the single write and the readback.
        # Never interleave a full-scan or heartbeat in this sequence.
        if _LAST_WRITE and time.monotonic() - _LAST_WRITE < MIN_WRITE_GAP:
            raise WriteConflictError("Nächster Schreibvorgang frühestens nach fünf Sekunden")
        client = _reader()
        limits = {"R01": ("R36", "R37"), "R02": ("R10", "R11"), "R03": ("R08", "R09")}
        codes = [code, *limits[code]] if code in limits else [code]
        curve_point = code in ("CP1-1","CP1-2","CP1-3","CP1-5","CP1-6","CP1-7")
        if curve_point or code == "compensate_offset":
            codes = list(dict.fromkeys([*codes,"H36","R10","R11"]))
        preflight = client.read_codes(codes)
        current = preflight.get(code)
        if not current:
            raise WriteValidationError("Aktueller Cloud-Wert nicht verfügbar; Schreiben verweigert")
        previous = _number(current["value"])
        if previous != expected_value:
            raise WriteConflictError("Wert wurde inzwischen geändert; bitte neu laden")
        if code in limits:
            low, high = limits[code]
            minimum, maximum = _limit(preflight.get(low), low), _limit(preflight.get(high), high)
            if minimum > maximum or not minimum <= desired <= maximum:
                raise WriteValidationError(f"{code}: außerhalb der aktuellen {low}/{high}-Grenzen")
        if code == "compensate_offset" and desired != previous:
            if "H36" not in preflight:
                raise WriteValidationError("AT-Kurvenmodus nicht lesbar")
            curve_point = _number(preflight["H36"]["value"]) == 2
        if curve_point and desired != previous:
            low, high = _limit(preflight.get("R10"),"R10"), _limit(preflight.get("R11"),"R11")
            if low > high or not low <= desired <= high:
                raise WriteValidationError("AT-Kurvenpunkt außerhalb der aktuellen R10/R11-Grenzen")
        if credentials() != account:
            raise WriteConflictError("Cloud-Konto während der Prüfung gewechselt")
        if desired == previous:
            return {"status": "unchanged", "confirmed": True, "code": code,
                    "value": float(desired)}
        if not client.token:
            raise CloudError("Keine authentifizierte Cloud-Verbindung")
        payload = {
            "appId": "16",
            "param": [{
                "deviceCode": client.device_code,
                "protocolCode": code,
                "value": wire_value,
            }],
        }
        # Set the cooldown BEFORE sending: an unclear timeout must never be
        # automatically repeated by this API.
        _LAST_WRITE = time.monotonic()
        log_event("write", "Cloud-Steuerbefehl einmalig gesendet")
        try:
            # Deliberately bypass _request_auth: that helper retries a request
            # after login renewal, unsafe for a potentially applied write.
            reply = client._post("app/device/control?lang=en", payload, token=client.token)
        except CloudError:
            log_event("warn", "Cloud-Schreibantwort unklar; kein automatischer Retry")
            return {"status": "unconfirmed", "confirmed": False, "code": code,
                    "message": "Cloud-Schreibantwort unklar; aktuellen Zustand neu lesen"}
        if not client._ok(reply):
            log_event("error", "Cloud-Schreibauftrag von API nicht bestätigt")
            return {"status": "rejected", "confirmed": False, "code": code,
                    "message": "Cloud hat Steuerauftrag nicht bestätigt"}
        if credentials() != account:
            return {"status": "unconfirmed", "confirmed": False, "code": code,
                    "message": "Cloud-Konto gewechselt; Readback verworfen"}
        time.sleep(0.8)
        try:
            fresh = client.read_codes([code])
        except CloudError:
            log_event("warn", "Cloud-Readback nicht verfügbar")
            return {"status": "unconfirmed", "confirmed": False, "code": code,
                    "message": "Steuerauftrag angenommen, aber Readback nicht verfügbar"}
        row = fresh.get(code)
        if not row or credentials() != account:
            return {"status": "unconfirmed", "confirmed": False, "code": code,
                    "message": "Kein gültiger Readback; nicht erneut senden"}
        merge({code: row}, source=account)
        try:
            actual = _number(row["value"])
        except WriteValidationError:
            actual = None
        if actual is not None and abs(actual - desired) <= (Decimal("0.05") if code == "R02" else 0):
            log_event("write", "Cloud-Schreibwert per Readback bestätigt")
            return {"status": "confirmed", "confirmed": True, "code": code,
                    "value": float(actual)}
        log_event("warn", "Cloud-Readback weicht vom angeforderten Wert ab")
        return {"status": "unconfirmed", "confirmed": False, "code": code,
                "message": "Cloud-Readback abweichend; Gerät nicht erneut beschreiben"}
