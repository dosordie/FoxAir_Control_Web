#!/usr/bin/env bash
# One-time setup for the standalone FoxAir Web service. No other services touched.
set -euo pipefail
if (( EUID != 0 )); then echo "Bitte als root ausführen." >&2; exit 1; fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$ROOT" != /opt/foxair-web/app ]]; then
  echo "Dieses Beispiel setzt den Installationsort /opt/foxair-web/app voraus." >&2
  echo "Für andere Pfade muss die systemd-Einheit angepasst werden." >&2
  exit 1
fi
if [[ ! -s "$ROOT/frontend/dist/index.html" || ! -x /opt/foxair-web/venv/bin/python ]]; then
  echo "Zuerst bash scripts/update.sh ausführen (Frontend und venv erforderlich)." >&2
  exit 1
fi
if ! id -u foxair-web >/dev/null 2>&1; then
  useradd --system --shell /usr/sbin/nologin foxair-web
fi
UNIT=/etc/systemd/system/foxair-web.service
if [[ -e "$UNIT" ]]; then
  echo "Bestehende FoxAir-Servicekonfiguration bleibt unverändert: $UNIT"
else
  cat > "$UNIT" <<'EOF'
[Unit]
Description=FoxAir Control Web
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=foxair-web
Group=foxair-web
WorkingDirectory=/opt/foxair-web/app
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/foxair-web/venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8081
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
CPUWeight=25
MemoryMax=256M

[Install]
WantedBy=multi-user.target
EOF
  chmod 0644 "$UNIT"
  echo "FoxAir-Dienst neu angelegt."
fi
bash "$ROOT/scripts/install_stream_shutdown.sh"
systemctl daemon-reload
systemctl start foxair-web.service
echo "Nur FoxAir gestartet. Automatisch beim Boot starten mit:"
echo "  systemctl enable foxair-web.service"
echo "Status: systemctl status foxair-web.service --no-pager"
echo "Test:   curl -fsS http://127.0.0.1:8081/api/health"
