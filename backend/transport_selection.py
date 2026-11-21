"""One persistent transport choice for the installation, with serialized bus handover."""

from contextlib import contextmanager
import threading
from backend import cloud_config

LOCK = threading.RLock()
IDS = {"cloud", "warmlink_raw", "display_modbus", "standard_modbus"}


def stored():
    row = cloud_config._read_json(cloud_config.STATE_DIR / "active_transport.json")
    return row if row.get("transport") in IDS else None


def allows(transport):
    row = stored()
    # Standalone clients/tests without the application lifespan retain legacy use.
    return row is None or row["transport"] == transport


def initialize():
    from backend.settings import display_endpoint, warmlink_endpoint, standard_endpoint

    row = stored()
    if row:
        return row
    with LOCK:
        row = stored()
        if row:
            return row
        transport = (
            "display_modbus"
            if display_endpoint()
            else "warmlink_raw"
            if warmlink_endpoint()
            else "standard_modbus"
            if standard_endpoint()
            else "cloud"
        )
        row = {"transport": transport, "revision": 1}
        cloud_config._atomic_json(cloud_config.STATE_DIR / "active_transport.json", row)
        return row


@contextmanager
def operation(transport):
    with LOCK:
        if not allows(transport):
            raise ValueError(
                "Andere Verbindung ist global ausgewählt; Auswahl wird synchronisiert"
            )
        yield


def select(transport):
    from backend.settings import display_endpoint, warmlink_endpoint, standard_endpoint
    from backend.bus_connection import manager as lte
    from backend.display_bus import manager as display
    from backend.register_scan import scan
    from backend.rtu import standard_connection

    if transport not in IDS:
        raise ValueError("Unbekannte Verbindung")
    endpoints = {
        "display_modbus": display_endpoint,
        "warmlink_raw": warmlink_endpoint,
        "standard_modbus": standard_endpoint,
    }
    if transport in endpoints and endpoints[transport]() is None:
        raise ValueError("Verbindung zuerst in den Verbindungseinstellungen aktivieren")
    scan.stop(timeout=0)
    with LOCK:
        old = initialize()
        if old["transport"] == transport:
            return old
        # In-flight RTU operations hold LOCK. Close receivers before publishing
        # the new choice, so a second physical bus cannot start in parallel.
        lte.disconnect()
        display.disconnect()
        standard_connection.disconnect()
        row = {"transport": transport, "revision": old["revision"] + 1}
        cloud_config._atomic_json(cloud_config.STATE_DIR / "active_transport.json", row)
        return row
