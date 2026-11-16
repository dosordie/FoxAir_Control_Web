#!/usr/bin/env python3
"""One-time, interactive admin-password bootstrap. Never puts password in Git."""
from __future__ import annotations
import getpass
import os
from pathlib import Path
import pwd
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if os.geteuid() != 0:
    raise SystemExit("Nur als root ausführen")
if not Path("/etc/systemd/system/foxair-web.service").is_file():
    raise SystemExit("Zuerst FoxAir-Dienst installieren")
from backend.cloud_config import STATE_DIR, set_admin_password

pw = getpass.getpass("Neues FoxAir-Web-Administrationspasswort (mind. 12 Zeichen): ")
pw2 = getpass.getpass("Wiederholen: ")
if pw != pw2:
    raise SystemExit("Passwörter stimmen nicht überein")
STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
uid = pwd.getpwnam("foxair-web").pw_uid
gid = pwd.getpwnam("foxair-web").pw_gid
os.chown(STATE_DIR, uid, gid)
os.chmod(STATE_DIR, 0o700)
set_admin_password(pw)
os.chown(STATE_DIR / "admin.json", uid, gid)

# The standalone FoxAir unit uses ProtectSystem=strict. Allow writes only to
# the dedicated FoxAir state directory so the web UI can atomically update
# its own cloud.json, while the rest of the system remains read-only.
import subprocess
DROPIN_DIR = Path("/etc/systemd/system/foxair-web.service.d")
DROPIN_DIR.mkdir(parents=True, exist_ok=True)
DROPIN = DROPIN_DIR / "40-cloud-state.conf"
DROPIN.write_text(
    "[Service]\nReadWritePaths=" + str(STATE_DIR) + "\n",
    encoding="utf-8",
)
os.chmod(DROPIN, 0o644)
subprocess.run(["systemctl", "daemon-reload"], check=True)
if subprocess.run(["systemctl", "is-active", "--quiet", "foxair-web.service"]).returncode == 0:
    subprocess.run(["systemctl", "restart", "foxair-web.service"], check=True)
print("Admin-Passwort und Schreibfreigabe nur für FoxAir-State eingerichtet.")
print("Web-Einstellungen ausschließlich über HTTPS oder SSH-Tunnel verwenden.")
