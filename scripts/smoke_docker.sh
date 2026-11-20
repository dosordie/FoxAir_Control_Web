#!/usr/bin/env bash
# Disposable CI container only. No real heat-pump endpoint is configured.
set -euo pipefail
image="${1:?image required}"
name="foxair-smoke-${GITHUB_RUN_ID:-local}"
volume="$name-state"
docker volume create "$volume" >/dev/null
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; docker volume rm "$volume" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --name "$name" --read-only --tmpfs /tmp -p 127.0.0.1:18081:8081 -v "$volume:/var/lib/foxair-web" "$image" >/dev/null
for i in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:18081/api/health >/tmp/foxair-smoke-health.json; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:18081/ | grep -qi '<html'
curl -fsS http://127.0.0.1:18081/sw.js >/dev/null
curl -fsS http://127.0.0.1:18081/cloud_catalog.json >/dev/null
docker exec -i "$name" python - <<'PY'
import json, urllib.request
from backend import cloud_config
def call(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:8081'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-FoxAir-Admin':'1'})
    return json.load(urllib.request.urlopen(request))
assert call('/api/setup/status')['required']
code=cloud_config._read_json(cloud_config.STATE_DIR/'setup-code.json')['code']
call('/api/setup/complete',{'code':code,'password':'ci-only-unique-password'})
assert cloud_config.verify_admin('ci-only-unique-password')
assert not call('/api/setup/status')['required']
assert call('/api/admin/login',{'admin_password':'ci-only-unique-password'})['authenticated']
health=call('/api/health')
assert health['build']['build_consistent']
assert health['build']['source_commit']==health['build']['frontend_source_commit']
cloud_config._atomic_json(cloud_config.STATE_DIR/'ci-persistence.json',{'kept':True})
PY
docker restart "$name" >/dev/null
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18081/api/health >/tmp/foxair-smoke-health.json; then break; fi
  sleep 1
done
docker exec "$name" python -c "from backend import cloud_config; assert cloud_config.verify_admin('ci-only-unique-password'); assert cloud_config._read_json(cloud_config.STATE_DIR/'ci-persistence.json')['kept']"
test "$(docker image inspect "$image" --format '{{.Config.User}}')" = '10001:10001'
export EXPECTED_VERSION="$(docker image inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.version"}}')"
export EXPECTED_SOURCE="$(docker image inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
python - <<'PY'
import json,os
d=json.load(open('/tmp/foxair-smoke-health.json'))['build']
assert d['source_commit']==os.environ.get('FOXAIR_EXPECTED_SOURCE',os.environ['GITHUB_SHA'])==os.environ['EXPECTED_SOURCE']
assert d['version']==os.environ['EXPECTED_VERSION']
PY
docker stop --time 20 "$name" >/dev/null
test "$(docker inspect "$name" --format '{{.State.ExitCode}}')" = '0'

docker rm "$name" >/dev/null
docker run -d --name "$name" --read-only --tmpfs /tmp -p 127.0.0.1:18081:8081 -v "$volume:/var/lib/foxair-web" "$image" >/dev/null
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18081/api/health >/dev/null; then break; fi
  sleep 1
done
docker exec "$name" python -c "from backend import cloud_config; assert cloud_config.verify_admin('ci-only-unique-password'); assert cloud_config._read_json(cloud_config.STATE_DIR/'ci-persistence.json')['kept']; assert cloud_config._read_json(cloud_config.STATE_DIR/'admin-sessions.json')"
for i in $(seq 1 40); do
  if [[ "$(docker inspect "$name" --format '{{.State.Health.Status}}')" == healthy ]]; then break; fi
  sleep 1
done
test "$(docker inspect "$name" --format '{{.State.Health.Status}}')" = healthy
docker stop --time 20 "$name" >/dev/null
test "$(docker inspect "$name" --format '{{.State.ExitCode}}')" = '0'
