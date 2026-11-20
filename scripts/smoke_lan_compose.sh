#!/usr/bin/env bash
# Start the release Compose definition on a private runner address.
set -euo pipefail
export FOXAIR_PREVIEW_IMAGE="${1:?local image required}"
compose=(docker compose -p foxair-lan-smoke -f compose.preview.yaml)
address=192.168.253.1
sudo ip addr add "$address/32" dev lo
cleanup() {
  "${compose[@]}" down --volumes
  sudo ip addr del "$address/32" dev lo
}
trap cleanup EXIT
"${compose[@]}" up -d --pull never
base="http://$address:18081"
curl -fsS --retry 10 --retry-connrefused --retry-delay 1 "$base/api/health" >/dev/null
if [[ "$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: example.invalid' "$base/")" != 403 ]]; then
  echo "Foreign Host must be rejected" >&2
  exit 1
fi
# Keep the test-only setup code in process memory.
"${compose[@]}" exec -T foxair-web cat /var/lib/foxair-web/setup-code.json |
  python -c '
import http.cookiejar, json, sys, urllib.request
base = sys.argv[1]
code = json.load(sys.stdin)["code"]
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(path, data=None):
    request = urllib.request.Request(
        base + path, data=json.dumps(data).encode() if data is not None else None,
        headers={"Origin": base, "Content-Type": "application/json", "X-FoxAir-Admin": "1"},
    )
    with browser.open(request, timeout=5) as response:
        return json.load(response)
assert call("/api/setup/status")["lan_http"]
assert call("/api/setup/complete", {"code": code, "password": "ci-preview-test-password"})["configured"]
assert call("/api/admin/session")["lan_http"]
assert call("/api/admin/login", {"admin_password": "ci-preview-test-password"})["authenticated"]
assert call("/api/admin/session")["authenticated"]
' "$base"
