"""Register information comes from FoxAir_Control JSON snapshots, not manual copies."""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@lru_cache(maxsize=1)
def load_registers() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in ("foxair_phnix_registers.json", "foxair_phnix_display_registers.json"):
        path = DATA_DIR / name
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for number, item in data.items():
            if number.isdigit() and isinstance(item, dict):
                # Do not let display-only definitions overwrite MAIN register IDs.
                result.setdefault(number, dict(item))
    extra = DATA_DIR / "foxair_phnix_knowledge.json"
    if extra.is_file():
        knowledge = json.loads(extra.read_text(encoding="utf-8"))
        for number, item in knowledge.items():
            if number in result and isinstance(item, dict):
                result[number].setdefault("description", item.get("description", ""))
    return result


def register_group(entry: dict, number: str = "") -> str:
    """Use source catalog block; infer reviewed code prefix only as fallback."""
    block = str(entry.get("block") or "").strip().upper()
    if block:
        return block
    code = str(entry.get("code") or "").strip().upper()
    if code:
        import re
        result = re.match(r"^[A-Z]+", code)
        if result:
            return result.group(0)
    # Unmapped status / diagnostics are explicitly not promoted to T-group.
    n = int(number or 0)
    if 2000 <= n < 3000:
        return "STATUS"
    if n >= 6000:
        return "DIAG"
    return "OTHER"


def group_counts() -> list[dict]:
    counts: dict[str, int] = {}
    for num, entry in load_registers().items():
        grp = register_group(entry, num)
        counts[grp] = counts.get(grp, 0) + 1
    return [{"group": g, "count": counts[g]} for g in sorted(counts)]


def public_register(number: str, entry: dict) -> dict:
    return {
        "register": int(number),
        "code": entry.get("code") or "",
        "group": register_group(entry, number),
        "name": entry.get("name") or f"Register {number}",
        "description": entry.get("description") or entry.get("info") or entry.get("notes") or "",
        "unit": entry.get("unit") or ("°C" if entry.get("type") == "TEMP1" else ""),
        "type": entry.get("type") or "RAW",
        "mode": entry.get("mode") or "read",
        "value_map": entry.get("value_map") if isinstance(entry.get("value_map"), dict) else {},
        "write_available": False,  # Write availability is controlled per code in API.
    }


def search_registers(query: str = "", limit: int = 80, group: str = "") -> list[dict]:
    term = query.strip().casefold()
    out = []
    def code_key(item):
        code = str(item[1].get("code") or "").casefold()
        return (not bool(code), [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", code)], int(item[0]))

    for number, definition in sorted(load_registers().items(), key=code_key):
        row = public_register(number, definition)
        if group and row["group"].upper() != group.upper():
            continue
        if term and not any(term in str(row[key]).casefold() for key in ("register", "code", "name")):
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def format_raw(raw: int, entry: dict) -> tuple[object, str]:
    kind = str(entry.get("type") or "").upper()
    signed = raw - 0x10000 if raw >= 0x8000 else raw
    if kind == "TEMP1":
        return round(signed / 10.0, 1), "°C"
    if kind == "FLOW_M3H_X100":
        return round(raw / 100.0, 2), "m³/h"
    if kind == "FLOW_M3H_X10":
        return round(raw / 10.0, 1), "m³/h"
    mapping = entry.get("value_map")
    if isinstance(mapping, dict) and str(raw) in mapping:
        return mapping[str(raw)], entry.get("unit") or ""
    return signed if entry.get("signed") else raw, entry.get("unit") or ""
