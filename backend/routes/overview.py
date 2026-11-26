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
    | {
        "electrical_power",
        "thermal_power",
        "cop",
        "compressor_frequency",
        "timer_m1",
        "last_defrost",
    }
)
GLANCE_DEFAULT = [
    "electrical_power",
    "thermal_power",
    "cop",
    "gira",
    "power",
    "mode",
    "silent",
    "parameters",
]
GLANCE_ACTIONS = set(GLANCE_DEFAULT)
GLANCE_SPACERS = {f"spacer:{slot}" for slot in range(1, 7)}
LOCK = Lock()


def config_path():
    return cloud_config.STATE_DIR / "overview.json"


@router.get("/api/overview")
def settings():
    saved = cloud_config._read_json(config_path())
    mobile = ["return", "supply", "spread", "flow", "tank", "outdoor"]
    return {
        "mobile_glance": saved.get("mobile_glance", GLANCE_DEFAULT),
        "desktop_glance": saved.get("desktop_glance", GLANCE_DEFAULT),
        "mobile_columns": saved.get("mobile_columns", 3),
        "desktop_columns": saved.get("desktop_columns", 8),
        "mobile": saved.get("mobile", mobile),
        "desktop": saved.get("desktop", DEFAULT),
    }


class Layout(BaseModel):
    mobile: list[str]
    desktop: list[str]
    mobile_glance: list[str] | None = None
    desktop_glance: list[str] | None = None
    mobile_columns: int = Field(default=3, ge=1, le=4)
    desktop_columns: int = Field(default=8, ge=1, le=9)


@router.post("/api/overview")
def save(payload: Layout, request: Request):
    cloud_config.require_admin(request)
    with LOCK:
        profiles = {**settings(), **payload.model_dump(exclude_none=True)}
        validate_profiles(profiles)
        cloud_config._atomic_json(config_path(), profiles)
    return profiles


def validate_profiles(profiles):
    for name in ("mobile", "desktop", "mobile_glance", "desktop_glance"):
        keys = profiles[name]
        options = (
            OPTIONS | GLANCE_ACTIONS | GLANCE_SPACERS
            if name.endswith("_glance")
            else OPTIONS
        )
        if len(set(keys)) != len(keys) or any(
            key not in options and not re.fullmatch(r"gira:[0-9a-f]{24}", key)
            for key in keys
        ):
            raise HTTPException(422, "Ungültige oder doppelte Auswahl")


def standard_ranges(blocks):
    selected = settings()
    extra = sorted(
        {
            DASHBOARD_FIELDS[key]
            for keys in (
                selected["mobile"],
                selected["desktop"],
                selected["mobile_glance"],
                selected["desktop_glance"],
            )
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
