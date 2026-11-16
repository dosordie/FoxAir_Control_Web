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
print("Admin-Passwort konfiguriert. Für Browser-Einstellungen HTTPS oder SSH-Tunnel verwenden.")
