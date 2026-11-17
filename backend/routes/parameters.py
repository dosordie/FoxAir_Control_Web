"""Parameter navigation reads: fresh groups, coalesced FC03, no write authority."""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.last_values import store, remember_words
from backend.register_cache import is_public_register

router = APIRouter()


def blocks(registers):
    """Only adjacent requested words; at most 90 words per LTE request."""
    result = []
    for register in sorted(set(registers)):
        if result and result[-1][0] + result[-1][1] == register and result[-1][1] < 90:
            start, count = result[-1]
            result[-1] = (start, count + 1)
        else:
            result.append((register, 1))
    return result


class GroupRead(BaseModel):
    transport: str
    registers: list[int] = Field(max_length=200)


@router.post("/api/parameters/refresh")
def refresh_group(payload: GroupRead, request: Request):
    if request.headers.get("x-foxair-admin") != "1":
        raise HTTPException(403, "Anwendungs-Header fehlt")
    if payload.transport not in ("cloud", "warmlink_raw", "standard_modbus"):
        raise HTTPException(422, "Verbindung unterstützt keine aktiven Abfragen")
    known = store.values()
    now = datetime.now(timezone.utc)
    needed = []
    for register in sorted(set(payload.registers)):
        if not is_public_register(register):
            continue
        row = known.get(str(register))
        if (
            row
            and row.get("transport") == payload.transport
            and (now - datetime.fromisoformat(row["timestamp"])).total_seconds() <= 60
        ):
            continue
        needed.append(register)
    if not needed:
        return {"values": known, "updated": 0, "status": "current"}
    try:
        if payload.transport == "cloud":
            from backend.cloud_state import catalog, merge
            from backend.cloud_config import credentials
            from backend.cloud_read import _reader, _cloud_lock

            mappings = {
                item["register"]: item["code"]
                for item in catalog()
                if item.get("confidence") == "confirmed" or item.get("write_allowed")
            }
            codes = list(dict.fromkeys(mappings[r] for r in needed if r in mappings))
            with _cloud_lock:
                account = credentials()
                rows = _reader().read_codes(codes) if codes else {}
                merge(rows, source=account)
            updated = len(rows)
        else:
            from backend.settings import warmlink_endpoint, standard_endpoint
            from backend.warmlink import open_warmlink
            from backend.rtu import open_rtu
            from backend.register_scan import status

            if payload.transport == "warmlink_raw" and status()["status"] == "running":
                return {"values": known, "updated": 0, "status": "scanning"}
            endpoint = (
                warmlink_endpoint()
                if payload.transport == "warmlink_raw"
                else standard_endpoint()
            )
            if endpoint is None:
                raise ValueError("Modbus-Anschluss nicht eingerichtet")
            with (
                open_warmlink(endpoint)
                if payload.transport == "warmlink_raw"
                else open_rtu(endpoint)
            ) as session:
                for start, count in blocks(needed):
                    words = session.read_holding(start, count)
                    remember_words(endpoint, start, words, transport=payload.transport)
            updated = len(needed)
    except (RuntimeError, OSError, ValueError) as exc:
        # No replay after an ambiguous response. Existing values retain their age.
        raise HTTPException(
            502, "Gruppe nicht vollständig aktualisiert: " + str(exc)
        ) from None
    return {"values": store.values(), "updated": updated, "status": "updated"}


class ParameterWrite(BaseModel):
    transport: str
    expected_transport: str | None = None
    value: str = Field(max_length=64)
    expected: str = Field(max_length=64)


@router.post("/api/parameters/{register}/write")
def write_parameter(register: int, payload: ParameterWrite, request: Request):
    from backend.cloud_config import require_admin
    from backend.cloud_write import WriteValidationError, WriteConflictError
    from backend.cloud_read import CloudError
    from backend.parameter_write import write

    require_admin(request, "")
    try:
        return write(
            register,
            payload.transport,
            payload.value,
            payload.expected,
            expected_transport=payload.expected_transport,
        )
    except WriteConflictError as exc:
        raise HTTPException(409, str(exc)) from None
    except WriteValidationError as exc:
        raise HTTPException(422, str(exc)) from None
    except (OSError, ValueError, CloudError):
        raise HTTPException(
            502, "Parameterauftrag nicht abgeschlossen; Zustand neu lesen"
        ) from None
