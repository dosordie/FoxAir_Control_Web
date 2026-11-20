"""Interactive one-time Docker admin bootstrap (no systemd/root required)."""
from __future__ import annotations

import getpass

from backend.cloud_config import STATE_DIR, set_admin_password


def main() -> None:
    print("FoxAir Web Docker: lokales Admin-Passwort einrichten (mind. 12 Zeichen).")
    password = getpass.getpass("Neues Passwort: ")
    again = getpass.getpass("Wiederholen: ")
    if password != again:
        raise SystemExit("Passwoerter stimmen nicht ueberein")
    if len(password) < 12:
        raise SystemExit("Mindestens 12 Zeichen erforderlich")
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    set_admin_password(password)
    print("Admin-Passwort gespeichert. Bitte nur ueber HTTPS oder lokalen Tunnel anmelden.")


if __name__ == "__main__":
    main()
