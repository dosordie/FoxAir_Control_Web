"""Fixed server-side transport configuration. Never accept arbitrary hosts from browsers."""

from __future__ import annotations
from dataclasses import dataclass
import os
import ipaddress
import re
import stat
import threading

_config_lock = threading.RLock()
from backend.cloud_config import STATE_DIR, _read_json, _atomic_json

WARMLINK_FILE = STATE_DIR / "warmlink.json"


SERIAL_BAUDRATES = {
    "standard_modbus": 9600,
    "warmlink_raw": 9600,
    "display_modbus": 4800,
}
SERIAL_DEVICE = re.compile(
    r"/dev/(?:tty(?:USB|ACM)[0-9]+|(?:serial/by-(?:id|path)/|foxair-)[A-Za-z0-9_.:+-]+)"
)


def serial_fields(transport, row):
    return {
        "medium": row.get("medium", "tcp"),
        "serial_device": row.get("serial_device", ""),
        "baudrate": row.get("baudrate")
        if row.get("baudrate") is not None
        else SERIAL_BAUDRATES[transport],
    }


def validated_link(
    transport, *, host, port, enabled, medium="tcp", serial_device="", baudrate=None
):
    serial_device = serial_device.strip()
    fields = serial_fields(
        transport,
        {"medium": medium, "serial_device": serial_device, "baudrate": baudrate},
    )
    if medium not in ("tcp", "serial"):
        raise ValueError("Unbekannter Verbindungsweg")
    if not 1200 <= fields["baudrate"] <= 115200:
        raise ValueError("USB-Baudrate muss zwischen 1200 und 115200 liegen")
    if serial_device and (
        not SERIAL_DEVICE.fullmatch(serial_device)
        or serial_device.rsplit("/", 1)[1] in (".", "..")
    ):
        raise ValueError(
            "USB-Gerät als /dev/ttyUSB…, /dev/ttyACM…, /dev/serial/by-id/… oder /dev/foxair-… angeben"
        )
    if medium == "serial" and enabled and not serial_device:
        raise ValueError("USB-Gerätepfad fehlt")
    if not 1 <= port <= 65535:
        raise ValueError("TCP-Port muss zwischen 1 und 65535 liegen")
    if medium == "tcp" and (host or enabled):
        try:
            address = ipaddress.ip_address(host.strip())
        except ValueError:
            raise ValueError("Bitte eine gültige lokale IP-Adresse eingeben") from None
        if (
            not address.is_private
            or address.is_loopback
            or address.is_unspecified
            or address.is_multicast
        ):
            raise ValueError("Nur explizite private Bus-IP-Adressen erlaubt")
        host = str(address)
    return {"host": host, "port": port, **fields}


def endpoint_from_row(transport, row):
    if not row["enabled"]:
        return None
    if row["medium"] == "tcp":
        return Endpoint(row["host"], row["port"], row["slave"], row["timeout"])
    if row["medium"] != "serial" or not row["serial_device"]:
        return None
    return Endpoint(
        "",
        0,
        row["slave"],
        row["timeout"],
        "serial",
        row["serial_device"],
        row["baudrate"],
    )


def warmlink_config() -> dict:
    row = _read_json(WARMLINK_FILE)
    return {
        **serial_fields("warmlink_raw", row),
        "host": row.get("host", ""),
        "port": row.get("port", 2001),
        "idle_timeout_seconds": row.get("idle_timeout_seconds", 0),
        "browser_timeout_seconds": row.get("browser_timeout_seconds", 90),
        "enabled": row.get("enabled") is True,
        "slave": 99,
        "connection_mode": row.get("connection_mode", "on_demand"),
    }


def save_warmlink(
    host: str,
    port: int,
    enabled: bool,
    connection_mode: str = "on_demand",
    idle_timeout_seconds: int = 0,
    browser_timeout_seconds: int = 90,
    medium: str = "tcp",
    serial_device: str = "",
    baudrate: int | None = None,
) -> dict:

    if (
        not 0 <= idle_timeout_seconds <= 3600
        or not 30 <= browser_timeout_seconds <= 3600
    ):
        raise ValueError("Sitzungsdauer: 0–3600 Sekunden; Browser: 30–3600 Sekunden")
    if connection_mode not in ("on_demand", "browser", "permanent"):
        raise ValueError("Unbekannter Verbindungsmodus")
    link = validated_link(
        "warmlink_raw",
        host=host,
        port=port,
        enabled=enabled,
        medium=medium,
        serial_device=serial_device,
        baudrate=baudrate,
    )
    with _config_lock:
        if enabled:
            ensure_distinct_bus(Endpoint(**link), "warmlink_raw")
        _atomic_json(
            WARMLINK_FILE,
            {
                **link,
                "enabled": enabled,
                "connection_mode": connection_mode,
                "idle_timeout_seconds": idle_timeout_seconds,
                "browser_timeout_seconds": browser_timeout_seconds,
            },
        )
    return warmlink_config()


def warmlink_endpoint() -> Endpoint | None:
    return endpoint_from_row("warmlink_raw", {**warmlink_config(), "timeout": 5})


from backend.cloud_read import cloud_configured

TRANSPORTS = {
    "cloud": ("Cloud", "Cloud"),
    "standard_modbus": ("Modbus-Standard", "Modbus RTU"),
    "display_modbus": ("Modbus-Display", "Display"),
    "warmlink_raw": ("Modbus-LTE", "LTE-DTU"),
}


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    slave: int = 0x63
    timeout: float = 2.0
    medium: str = "tcp"
    serial_device: str = ""
    baudrate: int = 9600

    def connection_key(self):
        if self.medium == "tcp":
            return ("tcp", self.host, self.port)
        try:
            info = os.stat(self.serial_device)
            if stat.S_ISCHR(info.st_mode):
                return ("serial-device", info.st_rdev)
        except OSError:
            pass
        return ("serial-path", os.path.realpath(self.serial_device))


def local_bus_config(transport: str) -> dict:
    if transport not in ("display_modbus", "standard_modbus"):
        raise ValueError("Unbekannter lokaler Bus")
    row = _read_json(STATE_DIR / (transport + ".json"))
    legacy = transport == "standard_modbus" and not row
    return {
        **serial_fields(transport, row),
        "host": row.get(
            "host", os.getenv("FOXAIR_STANDARD_HOST", "") if legacy else ""
        ),
        "port": row.get(
            "port", int(os.getenv("FOXAIR_STANDARD_PORT", "2001")) if legacy else 2001
        ),
        "slave": row.get(
            "slave",
            int(os.getenv("FOXAIR_STANDARD_SLAVE", "99"), 0)
            if legacy
            else (3 if transport == "display_modbus" else 99),
        ),
        "timeout": row.get(
            "timeout",
            float(os.getenv("FOXAIR_STANDARD_TIMEOUT", "2.0")) if legacy else 2.0,
        ),
        "enabled": row.get("enabled") is True
        or (legacy and os.getenv("FOXAIR_ENABLE_STANDARD_MODBUS", "0") == "1"),
        "connection_mode": "browser"
        if transport == "standard_modbus"
        else row.get("connection_mode", "browser"),
        "browser_timeout_seconds": row.get("browser_timeout_seconds", 90),
    }


def local_endpoint(transport: str) -> Endpoint | None:
    row = local_bus_config(transport)
    if not row["enabled"] or (row["medium"] == "tcp" and not row["host"]):
        return None
    if (
        not 1 <= row["port"] <= 65535
        or not 1 <= row["slave"] <= 247
        or not 0.25 <= row["timeout"] <= 10
    ):
        raise ValueError("Ungültige Bus-Konfiguration")
    return endpoint_from_row(transport, row)


def display_endpoint() -> Endpoint | None:
    return local_endpoint("display_modbus")


def standard_endpoint() -> Endpoint | None:
    return local_endpoint("standard_modbus")


def ensure_distinct_bus(endpoint, transport):
    others = []
    if transport != "warmlink_raw":
        others.append(warmlink_endpoint())
    for other in ("display_modbus", "standard_modbus"):
        if other != transport:
            others.append(local_endpoint(other))
    if any(e and e.connection_key() == endpoint.connection_key() for e in others):
        raise ValueError(
            "Dieser Anschluss wird bereits von einem anderen Bus verwendet"
        )


def save_local_bus(
    transport: str,
    host: str,
    port: int,
    enabled: bool,
    slave: int = 3,
    timeout: float = 2.0,
    connection_mode: str = "browser",
    browser_timeout_seconds: int = 90,
    medium: str = "tcp",
    serial_device: str = "",
    baudrate: int | None = None,
):

    if transport not in (
        "display_modbus",
        "standard_modbus",
    ) or connection_mode not in ("browser", "permanent"):
        raise ValueError("Ungültige Buskonfiguration")
    if (
        not 1 <= port <= 65535
        or not 1 <= slave <= 247
        or not 0.25 <= timeout <= 10
        or not 30 <= browser_timeout_seconds <= 3600
    ):
        raise ValueError("Ungültiger Port, Teilnehmer oder Timeout")
    if transport == "display_modbus" and slave != 3:
        raise ValueError(
            "Display-Snapshot ist nur für das bestätigte Hauptdisplay (Unit 3) freigegeben"
        )
    link = validated_link(
        transport,
        host=host,
        port=port,
        enabled=enabled,
        medium=medium,
        serial_device=serial_device,
        baudrate=baudrate,
    )
    row = dict(
        **link,
        enabled=enabled,
        slave=slave,
        timeout=timeout,
        connection_mode=connection_mode,
        browser_timeout_seconds=browser_timeout_seconds,
    )
    with _config_lock:
        if enabled:
            ensure_distinct_bus(Endpoint(**link), transport)
        _atomic_json(STATE_DIR / (transport + ".json"), row)
    return local_bus_config(transport)


def transport_info() -> list[dict]:
    configured = standard_endpoint() is not None
    cloud_enabled = cloud_configured()
    lte_enabled = warmlink_endpoint() is not None
    display_enabled = display_endpoint() is not None
    return [
        {
            "id": "cloud",
            "name": "Cloud",
            "configured": cloud_enabled,
            "read_supported": cloud_enabled,
            "reason": ""
            if cloud_enabled
            else "Cloud-Zugangsdaten serverseitig noch nicht konfiguriert",
        },
        {
            "id": "standard_modbus",
            "name": "Modbus-Standard",
            "configured": configured,
            "read_supported": configured,
            "reason": ""
            if configured
            else "Modbus-Standard deaktiviert (separater Bus kann belegt sein)",
        },
        {
            "id": "warmlink_raw",
            "name": "Modbus-LTE",
            "configured": lte_enabled,
            "read_supported": lte_enabled,
            "reason": ""
            if lte_enabled
            else "LTE-Anschluss in den Einstellungen aktivieren",
        },
        {
            "id": "display_modbus",
            "name": "Modbus-Display",
            "configured": display_enabled,
            "read_supported": display_enabled,
            "reason": ""
            if display_enabled
            else "Display-Anschluss in den Einstellungen aktivieren",
        },
    ]
