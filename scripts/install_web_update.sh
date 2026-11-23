#!/usr/bin/env bash
# Install a dedicated *FoxAir-only* systemd .path -> .service updater.
# No sudoers, no privilege escalation by the unprivileged web process.
set -euo pipefail

if (( EUID != 0 )); then
  echo "Bitte als root ausführen." >&2
  exit 1
fi

app=/opt/foxair-web/app
state=/var/lib/foxair-web
unitdir=/etc/systemd/system
if [[ ! -f "$unitdir/foxair-web.service" || ! -f "$app/scripts/update.sh" ]]; then
  echo "FoxAir Web muss vor dem Updater installiert sein." >&2
  exit 1
fi

# The code executed as root must remain root-owned and not be editable by
# foxair-web, group users or other nonroot accounts.
python3 - "$app" <<'PY'
from pathlib import Path
import os, stat, sys
base = Path(sys.argv[1])
# The release updater imports Python modules and uses this private venv.
# Verify the full executable code tree before enabling a root helper.
venv = base.parent / "venv"
paths = [base, *base.rglob("*"), venv, *venv.rglob("*")]
for candidate in paths:
    if candidate.is_symlink() and candidate not in (base, venv):
        continue
    mode = candidate.stat()
    if mode.st_uid != 0 or mode.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise SystemExit(f"Unzulässige Rechte für GUI-Updates: {candidate} (Eigentümer root, Gruppe und andere ohne Schreibrecht erforderlich)")
PY

updater=update.sh
updater_args=
if [[ -d "$app/.git" ]]; then
  origin="$(git -C "$app" remote get-url origin)"
  case "$origin" in
    https://github.com/dosordie/FoxAir_Control_Web|https://github.com/dosordie/FoxAir_Control_Web.git|git@github.com:dosordie/FoxAir_Control_Web.git) ;;
    *) echo "Unerwartete Git-Quelle; Update-Auslöser nicht installiert." >&2; exit 1 ;;
  esac
  if [[ "$(git -C "$app" branch --show-current)" == work ]]; then
    updater=update-work.sh
    updater_args=--skip-unit-setup
    bash "$app/scripts/install_stream_shutdown.sh"
  fi
else
  # Release packages deliberately contain no mutable Git checkout.
  (cd "$app" && /opt/foxair-web/venv/bin/python -c "from backend.build_info import info; d=info(); assert d['build_consistent'] and d['build_channel']=='release'")
fi

install -d -m 0700 -o foxair-web -g foxair-web "$state"

cat > "$unitdir/foxair-web-update.service" <<EOF
[Unit]
Description=Update FoxAir Control Web
Wants=network-online.target
After=network-online.target
ConditionPathExists=/var/lib/foxair-web/update-request

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/foxair-web/app
ExecStartPre=/usr/bin/rm -f /var/lib/foxair-web/update-request
ExecStart=/usr/bin/bash /opt/foxair-web/app/scripts/$updater $updater_args
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/opt/foxair-web /var/lib/foxair-web
RestrictSUIDSGID=true
CPUWeight=20
CPUQuota=30%
Nice=10
IOSchedulingClass=idle
MemoryMax=256M
TimeoutStartSec=420
EOF

cat > "$unitdir/foxair-web-update.path" <<'EOF'
[Unit]
Description=Watch authorized FoxAir Web update requests

[Path]
PathExists=/var/lib/foxair-web/update-request
Unit=foxair-web-update.service

[Install]
WantedBy=multi-user.target
EOF

chmod 0644 "$unitdir/foxair-web-update.service" "$unitdir/foxair-web-update.path"
systemctl daemon-reload
systemctl enable --now foxair-web-update.path
echo "FoxAir-only Update-Pfad aktiviert."
echo "Web-App-Administrationspasswort schützt die Update-Anforderung."
