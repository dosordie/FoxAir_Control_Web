#!/usr/bin/env python3
"""Export source-pinned, read-only PHNIX code catalog from FoxAir_Control.

Run in CI with the public FoxAir_Control checkout as argument:
  python scripts/export_cloud_catalog.py upstream frontend/public/cloud_catalog.json

The output is deployed with the prebuilt Web UI. Never run upstream code,
download unpinned scripts, or write any credentials on the LXC at runtime.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

if len(sys.argv) != 3:
    raise SystemExit("Usage: export_cloud_catalog.py <upstream_dir> <output_json>")

upstream = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
if not (upstream / "cloud" / "warmlink_codes.py").exists():
    raise SystemExit("Upstream cloud catalog missing")

sys.path.insert(0, str(upstream))
from cloud.warmlink_codes import (
    WARMLINK_644_DISCOVERY_CODES, merged_cloud_metadata,
    code_name,
)
from cloud.warmlink_ios308_catalog import WARMLINK_IOS308_CODE_SET
from cloud.register_resolver import resolve_cloud_projection_register
from cloud.cloud_write_helpers import cloud_code_for_register, cloud_code_is_write_candidate
from cloud.warmlink_codes import cloud_hint
from cloud.metadata import resolve_cloud_range

registers_path = upstream / "data" / "foxair_phnix_registers.json"
registers = json.loads(registers_path.read_text(encoding="utf-8"))
rows = []
write_codes = {}
for code in WARMLINK_644_DISCOVERY_CODES:
    meta = merged_cloud_metadata(code)
    reg = resolve_cloud_projection_register(code, meta, registers)
    local = registers.get(str(reg), {}) if reg is not None else {}
    name = code_name(code)
    grp = str(local.get("block") or "").strip().upper() if local else ""
    cloud_type = "other"
    # Match desktop's confirmed mapping classification, not arbitrary T-prefix.
    if reg is not None and 2000 <= reg <= 2999:
        cloud_type = "live"
    elif reg is not None and 1000 <= reg <= 1999:
        cloud_type = "static"
    if code in {f"Fault{i}" for i in range(1, 11)}:
        cloud_type = "live"
    confidence = str(meta.get("confidence") or "")
    unit = str(meta.get("unit") or local.get("unit") or "")
    hint = cloud_hint(code)
    bounds = resolve_cloud_range(code, hint, {})
    if reg is not None and reg not in write_codes:
        write_codes[reg] = cloud_code_for_register(reg, require_write_allowed=True)
    rows.append({
        "write_allowed": cloud_code_is_write_candidate(code, hint),
        "write_code": write_codes.get(reg),
        "write_values": hint.get("write_values") or {},
        "write_min": bounds.minimum if bounds.confirmed and bounds.minimum != "" else None,
        "write_max": bounds.maximum if bounds.confirmed and bounds.maximum != "" else None,
        "code": code,
        "name": name or code,
        "register": reg,
        "group": grp or "CLOUD",
        "kind": cloud_type,
        "unit": unit,
        "confidence": confidence,
        "retry_when_empty": code in WARMLINK_IOS308_CODE_SET,
    })
if len(rows) < 400:
    raise SystemExit(f"Incomplete upstream catalog: {len(rows)}")
if len({x["code"] for x in rows}) != len(rows):
    raise SystemExit("Duplicate cloud codes")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"source": "dosordie/FoxAir_Control",
    "catalog": "WARMLINK_644_DISCOVERY_CODES", "items": rows},
    ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"Exported {len(rows)} reviewed Cloud candidates to {output}")
