"""Shared dashboard layout for mobile and tablet/desktop."""

import re
from threading import Lock

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend import cloud_config
from backend.register_definitions import DIAGNOSTIC_FIELDS, DASHBOARD_FIELDS

router = APIRouter()
DEFAULT = ["flow", "tank", "outdoor", "return", "supply", "spread"]
OPTIONS = (
    set(DEFAULT)
    | DIAGNOSTIC_FIELDS.keys()
    | {"electrical_power", "thermal_power", "cop", "compressor_frequency"}
)
LOCK = Lock()


def config_path():
    return cloud_config.STATE_DIR / "overview.json"


@router.get("/api/overview")
def settings():
    saved = cloud_config._read_json(config_path())
    mobile = ["return", "supply", "spread", "flow", "tank", "outdoor"]
    return {
        "mobile": saved.get("mobile", mobile),
        "desktop": saved.get("desktop", DEFAULT),
    }


class Layout(BaseModel):
    mobile: list[str] = Field(max_length=12)
    desktop: list[str] = Field(max_length=12)


@router.post("/api/overview")
def save(payload: Layout, request: Request):
    cloud_config.require_admin(request)
    profiles = payload.model_dump()
    for keys in profiles.values():
        if len(set(keys)) != len(keys) or any(
            key not in OPTIONS and not re.fullmatch(r"gira:[0-9a-f]{24}", key)
            for key in keys
        ):
            raise HTTPException(422, "Ungültige oder doppelte Auswahl")
    with LOCK:
        cloud_config._atomic_json(config_path(), profiles)
    return profiles


def standard_ranges(blocks):
    selected = settings()
    extra = sorted(
        {
            DASHBOARD_FIELDS[key]
            for keys in selected.values()
            for key in keys
            if key in DIAGNOSTIC_FIELDS
            and not any(
                start <= DASHBOARD_FIELDS[key] < start + size for start, size in blocks
            )
        }
    )
    ranges = []
    for register in extra:
        if ranges and register == sum(ranges[-1]):
            start, size = ranges[-1]
            ranges[-1] = start, size + 1
        else:
            ranges.append((register, 1))
    return blocks + tuple(ranges)
