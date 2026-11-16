#!/usr/bin/env python3
"""Set local PHNIX cloud credentials without ever storing them in GitHub.

Runs interactively as root; writes a systemd EnvironmentFile (0600) and a
service-specific drop-in. A restart is limited to the FoxAir service.
"""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import sys
import tempfile
import subprocess

SECRETS_DIR = Path("/etc/foxair-web")
ENV_FILE = SECRETS_DIR / "cloud.env"
DROPIN_DIR = Path("/etc/systemd/system/foxair-web.service.d")
DROPIN_FILE = DROPIN_DIR / "30-cloud-env.conf"


def quote_systemd(value: str) -> str:
    """Double-quoted EnvironmentFile assignment (no shell interpolation)."""
    if not value or any(c in value for c in ("\n", "\r", "\x00")):
        raise ValueError("Leere Werte, Zeilenumbrüche und NUL sind nicht zulässig")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("Bitte als root ausführen")
    if not Path("/etc/systemd/system/foxair-web.service").exists():
        raise SystemExit("Zuerst den eigenen FoxAir-Dienst einrichten")
    if not sys.stdin.isatty():
        raise SystemExit("Sicherheitsvorgabe: Konfiguration nur über eine interaktive Konsole")

    print("FoxAir Cloud – lokale Konfiguration (nur read-only).")
    print("Die Werte werden nicht ins Git-Repository übertragen.")
    username = input("PHNIX/WarmLink-Benutzer: ").strip()
    password = getpass.getpass("PHNIX/WarmLink-Passwort (unsichtbar): ")
    device = input("PHNIX-Gerätekennung (deviceCode): ").strip()
    assignments = {
        "FOXAIR_CLOUD_USER": username,
        "FOXAIR_CLOUD_PASSWORD": password,
        "FOXAIR_CLOUD_DEVICE_CODE": device,
    }
    try:
        text = "".join(f"{name}={quote_systemd(value)}\n" for name, value in assignments.items())
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    SECRETS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SECRETS_DIR, 0o700)

    # tempfile in the destination directory, atomic replace, restrictive perms.
    fd, name = tempfile.mkstemp(prefix=".cloud-", dir=SECRETS_DIR, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(name, 0o600)
        os.replace(name, ENV_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)

    DROPIN_DIR.mkdir(mode=0o755, parents=True, exist_ok=True)
    contents = "[Service]\nEnvironmentFile=/etc/foxair-web/cloud.env\n"
    temp_fd, temp_name = tempfile.mkstemp(prefix=".cloud-systemd-", dir=DROPIN_DIR, text=True)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as file:
            file.write(contents)
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, DROPIN_FILE)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    if subprocess.run(["systemctl", "is-active", "--quiet", "foxair-web.service"]).returncode == 0:
        subprocess.run(["systemctl", "restart", "foxair-web.service"], check=True)
        print("Nur foxair-web.service neu gestartet.")
    else:
        print("FoxAir-Dienst ist noch nicht gestartet; Konfiguration beim Start aktiv.")
    print("PHNIX-Cloud konfiguriert (keine Zugangsdaten ausgegeben).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
