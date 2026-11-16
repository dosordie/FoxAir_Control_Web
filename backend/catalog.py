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
    """Engineering values from FoxAir_Control 34ce0ed format_value_by_type.

    Only local Modbus words use this function; Cloud engineering values must
    never be scaled a second time. Unknown/ambiguous types remain raw.
    """
    kind = str(entry.get("type") or "").upper()
    signed = raw - 0x10000 if raw >= 0x8000 else raw
    unit=entry.get('unit') or ''
    mapping = entry.get("value_map")
    if isinstance(mapping,dict):
        for key in (str(raw),str(signed)):
            if key in mapping:return mapping[key],unit
    groups=(
        (('TEMP','TEMP1'),10,1,'°C'),
        (('TEMP05','TEMP_0_5','STEP_0_5C'),2,1,'°C'),
        (('POWER_KW_X10','KW_X10'),10,1,'kW'),
        (('BAR_X10','PRESSURE_BAR_X10'),10,1,'bar'),
        (('AMP_X2','CURRENT_A_X2'),2,1,'A'),
        (('AMP_X10','CURRENT_A_X10'),10,1,'A'),
        (('FLOW_M3H_X100','FLOW_X100'),100,2,'m³/h'),
        (('FLOW_M3H_X10','FLOW_X10'),10,1,'m³/h'),
        (('COP_X100','COP100'),100,2,''),
        (('DIGI5',),10,1,''), (('DIGI6',),1000,3,''),
        (('DIGI19',),100,2,''), (('DIGI4',),5,1,''),
    )
    for types,scale,precision,default_unit in groups:
        if kind in types:return round(signed/scale,precision),unit or default_unit
    if kind in ('TIME_HHMM','HHMM'):
        hour,minute=raw>>8,raw&255
        if hour<=23 and minute<=59:return f'{hour:02d}:{minute:02d}',unit
    if kind=='HZ_LOW8':return raw&255,unit or 'Hz'
    if kind in ('TEMP_OFFSET55','TEMP_OFFSET55_LOW8'):
        return (raw&(255 if kind.endswith('LOW8') else 65535))-55,unit or '°C'
    if kind=='YEAR_2000':return 2000+raw,unit
    signed_units={'VOLT':'V','VOLTS':'V','V':'V','WATT':'W','WATTS':'W','POWER_W':'W',
        'RPM':'rpm','FAN_RPM':'rpm','KWH':'kWh','ENERGY_KWH':'kWh','HZ':'Hz',
        'MINUTES':'min','SECONDS':'s','HOURS':'h','DAYS':'days','PERCENT':'%','STEPS_N':'N'}
    if kind in signed_units:return signed,unit or signed_units[kind]
    return signed if entry.get('signed') or kind in ('INT16','SIGNED INT16','DIGI1','DIGI9') else raw,unit
