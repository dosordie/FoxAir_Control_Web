#!/usr/bin/env bash
# Start the release Compose definition on a private runner address.
set -euo pipefail
export FOXAIR_PREVIEW_IMAGE="${1:?local image required}"
compose=(docker compose -p foxair-lan-smoke -f compose.preview.yaml)
address=192.168.253.1
host=foxair-test.invalid
unset FOXAIR_LAN_HOSTS
sudo sed -i "\$a$address $host" /etc/hosts
sudo ip addr add "$address/32" dev lo
cleanup() {
  "${compose[@]}" down --volumes
  sudo ip addr del "$address/32" dev lo
}
trap cleanup EXIT
"${compose[@]}" up -d --pull never
base="http://$host:18081"
export NO_PROXY="${NO_PROXY:-},$host,$address"
curl -fsS --retry 10 --retry-connrefused --retry-delay 1 "http://$address:18081/api/health" >/dev/null
curl -fsS "$base/api/health" >/dev/null
python -c '
import http.cookiejar, json, sys, urllib.error, urllib.request
base = sys.argv[1]
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(path, data=None, origin=None, host=None):
    request = urllib.request.Request(
        base + path, data=json.dumps(data).encode() if data is not None else None,
        headers={"Origin": base if origin is None else origin, "Content-Type": "application/json", "X-FoxAir-Admin": "1"},
    )
    if host is not None:
        request.add_header("Host", host)
    with browser.open(request, timeout=5) as response:
        return json.load(response)
status = call("/api/setup/status")
assert status["required"] and status["lan_http"] and not status["code_required"]
payload = {"password": "ci-preview-test-password"}
try:
    call("/api/setup/complete", payload, origin="http://other.invalid")
except urllib.error.HTTPError as e:
    assert e.code == 403
else:
    raise AssertionError("A foreign origin was accepted")
result = call("/api/setup/complete", payload)
assert result["configured"] and not result["login_required"]
assert call("/api/admin/session")["authenticated"]
call("/api/admin/logout", {})
assert call("/api/admin/login", {"admin_password": payload["password"]})["authenticated"]
assert call("/api/admin/session")["authenticated"]
assert call("/api/admin/lan-access/save", {"hosts": ["custom-foxair.invalid"]})["hosts"] == ["custom-foxair.invalid"]
assert call("/api/health", host="custom-foxair.invalid:18081")["ok"]
' "$base"
if [[ "$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: example.invalid' "http://$address:18081/")" != 403 ]]; then
  echo "Foreign Host must be rejected after setup" >&2
  exit 1
fi
