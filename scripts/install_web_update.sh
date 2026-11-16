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
for candidate in (base, base / "scripts", base / "scripts" / "update.sh", base / ".git"):
    mode = candidate.stat()
    if mode.st_uid != 0 or mode.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise SystemExit("Unsafe updater checkout permissions; keep FoxAir Git checkout root-owned")
PY

origin="$(git -C "$app" remote get-url origin)"
case "$origin" in
  https://github.com/dosordie/FoxAir_Control_Web|https://github.com/dosordie/FoxAir_Control_Web.git|git@github.com:dosordie/FoxAir_Control_Web.git)
    ;;
  *)
    echo "Unerwartete Git-Quelle: Update-Auslöser NICHT installiert." >&2
    exit 1 ;;
esac

install -d -m 0700 -o foxair-web -g foxair-web "$state"

cat > "$unitdir/foxair-web-update.service" <<'EOF'
[Unit]
Description=Update FoxAir Control Web from validated Git source
Wants=network-online.target
After=network-online.target
ConditionPathExists=/var/lib/foxair-web/update-request

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/foxair-web/app
ExecStartPre=/usr/bin/rm -f /var/lib/foxair-web/update-request
ExecStart=/usr/bin/bash /opt/foxair-web/app/scripts/update.sh
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/opt/foxair-web /var/lib/foxair-web
RestrictSUIDSGID=true
CPUWeight=20
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
