"""Fixed server-side transport configuration. Never accept arbitrary hosts from browsers."""
from __future__ import annotations
from dataclasses import dataclass
import os
from backend.cloud_config import STATE_DIR, _read_json, _atomic_json

WARMLINK_FILE = STATE_DIR / "warmlink.json"


def warmlink_config() -> dict:
    row = _read_json(WARMLINK_FILE)
    return {"host": row.get("host", "192.168.1.50"), "port": row.get("port", 2001),
            "enabled": row.get("enabled") is True, "slave": 99}


def save_warmlink(host: str, port: int, enabled: bool) -> dict:
    import ipaddress
    # Explicit raw TCP endpoint only; no URLs, paths, credentials or DNS rebinding.
    try:
        address = ipaddress.ip_address(host.strip())
    except ValueError:
        raise ValueError("Bitte eine gültige lokale IP-Adresse eingeben") from None
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast or not 1 <= port <= 65535:
        raise ValueError("Lokale IP-Adresse und TCP-Port 1–65535 erforderlich")
    _atomic_json(WARMLINK_FILE, {"host": str(address), "port": port, "enabled": enabled})
    return warmlink_config()


def warmlink_endpoint() -> Endpoint | None:
    row = warmlink_config()
    return Endpoint(row["host"], row["port"], slave=99, timeout=5) if row["enabled"] else None

from backend.cloud_read import cloud_configured

TRANSPORTS = {
    "cloud": ("PHNIX Cloud", "Cloud"),
    "standard_modbus": ("Standard-Modbus", "Modbus RTU"),
    "display_modbus": ("Display-Modbus", "Display"),
    "warmlink_raw": ("LTE-/Warmlink-Modbus", "LTE-DTU"),
}


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    slave: int = 0x63
    timeout: float = 2.0


def standard_endpoint() -> Endpoint | None:
    if os.getenv("FOXAIR_ENABLE_STANDARD_MODBUS", "0") != "1":
        return None
    host = os.getenv("FOXAIR_STANDARD_HOST", "").strip()
    if not host:
        return None
    port = int(os.getenv("FOXAIR_STANDARD_PORT", "0"))
    slave = int(os.getenv("FOXAIR_STANDARD_SLAVE", "99"), 0)
    timeout = float(os.getenv("FOXAIR_STANDARD_TIMEOUT", "2.0"))
    if not 1 <= port <= 65535 or not 1 <= slave <= 247 or not 0.25 <= timeout <= 10:
        raise ValueError("Ungültige Standard-Modbus-Serverkonfiguration")
    return Endpoint(host=host, port=port, slave=slave, timeout=timeout)


def transport_info() -> list[dict]:
    configured = (os.getenv("FOXAIR_ENABLE_STANDARD_MODBUS", "0") == "1"
                  and bool(os.getenv("FOXAIR_STANDARD_HOST", "").strip()))
    cloud_enabled = cloud_configured()
    lte_enabled = warmlink_endpoint() is not None
    return [
        {"id": "cloud", "name": "PHNIX Cloud", "configured": cloud_enabled,
         "read_supported": cloud_enabled,
         "reason": "" if cloud_enabled else "Cloud-Zugangsdaten serverseitig noch nicht konfiguriert"},
        {"id": "standard_modbus", "name": "Standard-Modbus", "configured": configured,
         "read_supported": configured,
         "reason": "" if configured else "Standard-Modbus deaktiviert (separater Bus kann belegt sein)"},
        {"id": "display_modbus", "name": "Display-Modbus", "configured": False,
         "read_supported": False, "reason": "Passiver/aktiver Displaybus-Adapter noch in Entwicklung"},
        {"id": "warmlink_raw", "name": "LTE-/Warmlink-Modbus", "configured": lte_enabled,
         "read_supported": lte_enabled, "reason": "" if lte_enabled else "LTE-Anschluss in den Einstellungen aktivieren"},
    ]
