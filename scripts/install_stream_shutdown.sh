#!/usr/bin/env bash
# Bound shutdown of FoxAir's long-lived SSE connections. Preserve listener and
# all other existing service settings; do not affect any other service.
set -euo pipefail
if (( EUID != 0 )); then echo "Bitte als root ausführen." >&2; exit 1; fi
unit=/etc/systemd/system/foxair-web.service
if [[ ! -f "$unit" ]]; then exit 0; fi
if ! grep -Eq '(uvicorn backend.main:app|backend\.server)' "$unit"; then
  echo "Unerwarteter FoxAir-Startbefehl; Stream-Konfiguration nicht geändert." >&2
  exit 1
fi
directory=/etc/systemd/system/foxair-web.service.d
mkdir -p "$directory"
temporary="$(mktemp "$directory/.stream-shutdown.XXXXXX")"
trap 'rm -f -- "$temporary"' EXIT
cat > "$temporary" <<'EOF'
[Service]
Environment="UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=5"
TimeoutStopSec=15
EOF
chmod 0644 "$temporary"
if ! cmp -s "$temporary" "$directory/60-stream-shutdown.conf"; then
  mv -f -- "$temporary" "$directory/60-stream-shutdown.conf"
  systemctl daemon-reload
fi
