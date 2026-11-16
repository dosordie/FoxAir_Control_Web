#!/usr/bin/env bash
# Allow admin HTTPS detection behind ONE explicitly trusted reverse proxy.
# Never trust arbitrary X-Forwarded-* headers from the LAN.
set -euo pipefail
if (( EUID != 0 )); then echo "Bitte als root ausführen" >&2; exit 1; fi
if (( $# != 1 )); then
  echo "Aufruf: bash scripts/set_trusted_proxy.sh <PRIVATE_PROXY_IPV4>" >&2
  exit 2
fi
proxy_ip="$1"
python3 - "$proxy_ip" <<'PY'
import ipaddress, sys
try:
    addr = ipaddress.ip_address(sys.argv[1])
    if addr.version != 4 or not addr.is_private or addr.is_loopback or addr.is_link_local:
        raise ValueError("not an RFC1918 LAN address")
    if not any(addr in ipaddress.ip_network(network) for network in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"
    )):
        raise ValueError("not an RFC1918 LAN address")
except ValueError as exc:
    raise SystemExit("Nur private IPv4-Adressen des Reverse-Proxys sind erlaubt") from exc
PY
unit=/etc/systemd/system/foxair-web.service
if [[ ! -f "$unit" ]]; then
  echo "FoxAir-Dienst nicht eingerichtet" >&2; exit 1
fi
if ! grep -q 'backend.main:app' "$unit"; then
  echo "Unerwarteter Dienst; nichts geändert" >&2; exit 1
fi
dropin=/etc/systemd/system/foxair-web.service.d
mkdir -p "$dropin"
tmp="$(mktemp "$dropin/.trusted-proxy.XXXXXX")"
trap 'rm -f -- "$tmp"' EXIT
printf '[Service]\nEnvironment="FOXAIR_TRUSTED_PROXY_IPS=%s"\n' "$proxy_ip" > "$tmp"
chmod 0644 "$tmp"
mv "$tmp" "$dropin/50-trusted-https-proxy.conf"
systemctl daemon-reload
if systemctl is-active --quiet foxair-web.service; then
  systemctl restart foxair-web.service
fi
echo "Reverse-Proxy-IP nur für FoxAir als vertrauenswürdig gesetzt."
echo "Der Proxy muss X-Forwarded-Proto: https und Host weitergeben."
