"""Manage additional names for direct Docker LAN access."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend import cloud_config, lan_access

router = APIRouter()


class LanHosts(BaseModel):
    hosts: list[str] = Field(max_length=32)


def lan_settings():
    return {
        "enabled": lan_access.enabled(),
        "hosts": lan_access.saved_hosts(),
        "configured_hosts": sorted(lan_access.configured_hosts()),
    }


@router.post("/api/admin/lan-access")
def lan_status(request: Request):
    cloud_config.require_admin(request)
    return lan_settings()


@router.post("/api/admin/lan-access/save")
def save_lan_hosts(payload: LanHosts, request: Request):
    cloud_config.require_admin(request)
    if not lan_access.enabled():
        raise HTTPException(409, "Direkter Docker-LAN-Zugriff ist deaktiviert.")
    try:
        hosts = lan_access.normalize_hosts(payload.hosts)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    cloud_config._atomic_json(cloud_config.STATE_DIR / "lan-access.json", {"hosts": hosts})
    return lan_settings()
