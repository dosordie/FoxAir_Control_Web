#!/usr/bin/env bash
# Configure the FoxAir HTTP listener without touching any other service.
# Example: sudo bash scripts/set_listen_address.sh 192.168.1.50
# Revert:  sudo bash scripts/set_listen_address.sh --local
set -euo pipefail

if (( EUID != 0 )); then
  echo "Bitte als root ausführen." >&2
  exit 1
fi

if (( $# != 1 )); then
  echo "Aufruf: sudo bash scripts/set_listen_address.sh <private-LAN-IP|--local>" >&2
  exit 2
fi

UNIT="foxair-web.service"
UNIT_FILE="/etc/systemd/system/$UNIT"
DROPIN_DIR="/etc/systemd/system/$UNIT.d"
DROPIN="$DROPIN_DIR/20-listen-address.conf"
HOST="$1"

if [[ ! -f "$UNIT_FILE" ]]; then
  echo "FoxAir-Systemdienst fehlt: $UNIT_FILE" >&2
  exit 1
fi

if [[ "$HOST" == "--local" ]]; then
  HOST="127.0.0.1"
else
  python3 - "$HOST" <<'PY'
import ipaddress
import sys
ip = ipaddress.ip_address(sys.argv[1])
if ip.version != 4 or not any(ip in net for net in (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)):
    raise SystemExit("Nur IPv4-Adressen aus privaten RFC1918-LANs erlaubt.")
PY
  if ! ip -4 -o addr show | awk -v addr="$HOST" '{split($4, a, "/"); if (a[1] == addr) found=1} END {exit !found}'; then
    echo "LAN-IP $HOST ist auf keiner Schnittstelle des Containers konfiguriert." >&2
    exit 1
  fi
fi

# Refuse to alter an unexpected unit. The override affects only the FoxAir command.
if ! grep -Eq '(uvicorn backend.main:app|backend\.server)' "$UNIT_FILE"; then
  echo "Die FoxAir-Dienstdatei hat nicht den erwarteten Uvicorn-Startbefehl." >&2
  exit 1
fi

mkdir -p "$DROPIN_DIR"
tmp="$(mktemp "$DROPIN_DIR/.listen.XXXXXX")"
backup=""
cleanup() {
  if [[ -e "$tmp" ]]; then rm -f -- "$tmp"; fi
  if [[ -n "$backup" && -e "$backup" ]]; then rm -f -- "$backup"; fi
}
trap cleanup EXIT
cat > "$tmp" <<EOF
[Service]
ExecStart=
ExecStart=/opt/foxair-web/venv/bin/python -m backend.server --host $HOST --port 8081
EOF
chmod 0644 "$tmp"

if [[ -f "$DROPIN" ]]; then
  backup="$(mktemp "$DROPIN_DIR/.previous.XXXXXX")"
  cp -p -- "$DROPIN" "$backup"
fi
mv -f -- "$tmp" "$DROPIN"
systemctl daemon-reload

if systemctl is-active --quiet "$UNIT"; then
  if ! systemctl restart "$UNIT"; then
    echo "FoxAir-Neustart fehlgeschlagen, vorherige Listenerkonfiguration wird wiederhergestellt." >&2
    if [[ -n "$backup" ]]; then cp -p -- "$backup" "$DROPIN"; else rm -f -- "$DROPIN"; fi
    systemctl daemon-reload
    systemctl restart "$UNIT" || true
    exit 1
  fi
else
  echo "FoxAir-Dienst läuft noch nicht; Konfiguration wirkt beim nächsten Start."
fi

echo "FoxAir-HTTP-Listener: $HOST:8081"
echo "Hinweis: Der MVP besitzt noch keine eigene Anmeldung. Nur in vertrauenswürdigem LAN freigeben und Port 8081 per Firewall begrenzen."
