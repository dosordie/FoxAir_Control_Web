"""Fixed server-side transport configuration. Never accept arbitrary hosts from browsers."""
from dataclasses import dataclass
import os

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
    configured = bool(os.getenv("FOXAIR_STANDARD_HOST", "").strip())
    return [
        {"id": "cloud", "name": "PHNIX Cloud", "configured": False,
         "read_supported": False, "reason": "Cloud-Adapter folgt in einer weiteren Etappe"},
        {"id": "standard_modbus", "name": "Standard-Modbus", "configured": configured,
         "read_supported": configured,
         "reason": "" if configured else "FOXAIR_STANDARD_HOST/PORT noch nicht konfiguriert"},
        {"id": "display_modbus", "name": "Display-Modbus", "configured": False,
         "read_supported": False, "reason": "Passiver/aktiver Displaybus-Adapter noch in Entwicklung"},
        {"id": "warmlink_raw", "name": "LTE-/Warmlink-Modbus", "configured": False,
         "read_supported": False, "reason": "Bus-Arbitrierung mit vorhandenem DTU-Master noch offen"},
    ]
