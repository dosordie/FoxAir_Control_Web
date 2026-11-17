"""Source-bound Modbus readings, independent of sockets, HTTP and worker threads."""

from datetime import datetime, timezone
import threading
import time
from typing import Callable

from backend.catalog import format_raw, load_registers, register_group
from backend.settings import Endpoint
from backend.register_definitions import LTE_INIT_BLOCKS

PACKET_STARTS = tuple(start for start, _count in LTE_INIT_BLOCKS)
STALE_AFTER_SECONDS = 300


def is_public_register(register: int) -> bool:
    """Exclude private packet headers, ASCII identities and virtual diagnostics."""
    if not any(start + 10 <= register < start + 90 for start in PACKET_STARTS):
        return False
    entry = load_registers().get(str(register))
    return entry is not None and str(entry.get("type", "")).upper() not in (
        "ASCII",
        "BLOCK",
    )


class RegisterCache:
    def __init__(self, clock: Callable[[], float] = time.time, on_record=None):
        self._clock = clock
        self._on_record = on_record
        self._lock = threading.RLock()
        self._source: Endpoint | None = None
        self._observed: dict[int, tuple[int, float]] = {}
        self._readings: dict[int, tuple[int, float]] = {}

    def select_source(self, endpoint: Endpoint) -> bool:
        with self._lock:
            if self._source == endpoint:
                return False
            self._observed.clear()
            self._readings.clear()
            self._source = endpoint
            return True

    def record(
        self,
        endpoint: Endpoint,
        start: int,
        words: list[int],
        *,
        observed: bool = False,
    ) -> None:
        with self._lock:
            if self._source != endpoint:
                return
            destination = self._observed if observed else self._readings
            now = self._clock()
            for offset, word in enumerate(words):
                destination[start + offset] = (word, now)
            if self._on_record:
                self._on_record(endpoint, start, words, timestamp=now)

    def observe_frames(self, endpoint: Endpoint, frames: list[tuple]) -> None:
        for frame in frames:
            slave, function, start, count, payload, *rest = frame
            if function != 16 or frame[9] != "word-frame" or slave not in (0, 99):
                continue
            data = payload[1:]
            if len(data) == count * 2:
                self.record(
                    endpoint,
                    start,
                    [
                        int.from_bytes(data[i : i + 2], "big")
                        for i in range(0, len(data), 2)
                    ],
                    observed=True,
                )

    def observed_words(self) -> dict:
        with self._lock:
            return {
                str(register): {
                    "raw": raw,
                    "age_seconds": round(self._clock() - stamp, 1),
                    "quality": "observed",
                }
                for register, (raw, stamp) in self._observed.items()
                if is_public_register(register)
            }

    def values(self, endpoint: Endpoint | None, *, connected: bool) -> dict:
        with self._lock:
            if endpoint is None or self._source != endpoint:
                return {}
            observed, active = dict(self._observed), dict(self._readings)
        definitions = load_registers()
        result = {}
        now = self._clock()
        for register in observed.keys() | active.keys():
            if not is_public_register(register):
                continue
            raw, stamp = observed.get(register, (None, 0))
            quality = "observed"
            if register in active and active[register][1] >= stamp:
                raw, stamp = active[register]
                quality = "fresh"
            if now - stamp > STALE_AFTER_SECONDS or (
                quality == "observed" and not connected
            ):
                quality = "stale"
            entry = definitions[str(register)]
            value, unit = format_raw(raw, entry)
            result[str(register)] = {
                "register": register,
                "raw": raw,
                "value": value,
                "unit": unit,
                "quality": quality,
                "timestamp": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                "transport": "warmlink_raw",
                "code": entry.get("code") or "",
                "name": entry.get("name") or f"Register {register}",
                "group": register_group(entry, str(register)),
            }
        return result

    def metrics(
        self, fields: dict[str, int], endpoint: Endpoint | None, *, connected: bool
    ) -> dict:
        values = self.values(endpoint, connected=connected)

        def metric(register):
            row = values.get(str(register))
            return (
                {
                    key: row[key]
                    for key in ("value", "unit", "raw", "timestamp", "quality")
                }
                if row
                else None
            )

        result = {
            name: item
            for name, register in fields.items()
            if (item := metric(register)) is not None
        }
        selected = metric(2014)
        if (
            selected
            and selected["quality"] != "stale"
            and isinstance(selected["value"], (float, int))
            and 5 <= selected["value"] <= 80
        ):
            result["target"] = {
                **selected,
                "source_code": "2014",
                "label": "Aktueller Wassersollwert",
            }
        elif "target" in result:
            result["target"].update(source_code="R02", label="Heizungs-Basissollwert")
        return result
