#!/usr/bin/env bash
# Update work + matching prebuilt Git frontend, without Node on the server.
set -euo pipefail

NO_RESTART=0
SKIP_UNIT_SETUP=0
case "${1:-}" in
  "") ;;
  --no-restart) NO_RESTART=1 ;;
  --skip-unit-setup) SKIP_UNIT_SETUP=1 ;;
  -h|--help)
    echo "Usage: sudo bash scripts/update-work.sh [--no-restart]"
    exit 0 ;;
  *) echo "Unknown option" >&2; exit 2 ;;
esac

if (( EUID != 0 )); then
  echo "Bitte als root ausführen: sudo bash scripts/update-work.sh" >&2
  exit 1
fi

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(git branch --show-current)" != work ]]; then
  echo "Update nur aus Git-Branch work erlaubt." >&2
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Lokale Änderungen vorhanden; Update ohne Überschreiben abgebrochen." >&2
  exit 1
fi

echo "==> work und passenden Build vor Installation prüfen"
git fetch --no-tags origin work
previous_head="$(git rev-parse HEAD)"
source_sha="$(git rev-parse origin/work)"
if ! git merge-base --is-ancestor "$previous_head" "$source_sha" && [[ "$(git rev-parse --is-shallow-repository)" == true ]]; then
  git fetch --unshallow --no-tags origin work
  source_sha="$(git rev-parse origin/work)"
fi
if ! git merge-base --is-ancestor "$previous_head" "$source_sha"; then
  echo "Das Update ist kein Fast-Forward. Der Dienst bleibt in seinem aktuellen Zustand." >&2
  exit 1
fi

echo "==> Fertiges Frontend aus separatem Git-Build-Branch laden"
# The artifact branch uses unrelated commits. Never follow tags into the source
# history during this shallow fetch.
git fetch --no-tags --depth=1 origin +refs/heads/web-dist-work:refs/remotes/origin/web-dist-work
if ! git merge-base --is-ancestor "$previous_head" "$source_sha"; then
  echo "Die Quellhistorie stimmt nach dem Frontend-Abruf nicht mehr. FoxAir laeuft weiter." >&2
  exit 1
fi
build_sha="$(git show refs/remotes/origin/web-dist-work:.build-source-sha | tr -d '\r\n')"

if [[ "$build_sha" != "$source_sha" ]]; then
  echo "Web-Build ist für $build_sha, work hat $source_sha." >&2
  echo "CI-Build für diesen work-Commit noch nicht veröffentlicht. Später erneut ausführen." >&2
  exit 1
fi

dist_parent="$ROOT/frontend"
dist="$dist_parent/dist"
stage="$(mktemp -d "$dist_parent/.dist-stage.XXXXXX")"
backup="$dist_parent/.dist-previous"
was_active=0
cleanup() {
  local status=$?
  if [[ -n "${stage:-}" && -d "$stage" ]]; then rm -rf -- "$stage"; fi
  if (( status != 0 && was_active == 1 )) &&
     [[ "$(git rev-parse HEAD)" == "$previous_head" ]] &&
     ! systemctl is-active --quiet foxair-web.service; then
    echo "Update abgebrochen. Bisherigen FoxAir-Dienst wieder starten." >&2
    systemctl start foxair-web.service || true
  fi
  return "$status"
}
trap cleanup EXIT

echo "==> Frontend für Installation prüfen"
git archive refs/remotes/origin/web-dist-work | tar -x -C "$stage"
test -s "$stage/index.html" && test -d "$stage/assets" || {
  echo "Build ohne index.html oder Assets; keine Installation." >&2
  exit 1
}
chmod -R a+rX,go-w "$stage"

if (( NO_RESTART == 0 )) && systemctl is-active --quiet foxair-web.service; then
  was_active=1
  systemctl stop foxair-web.service
fi
git merge --ff-only "$source_sha"
venv="$ROOT/../venv"
if [[ ! -x "$venv/bin/python" ]]; then
  echo "Python-venv fehlt: $venv" >&2
  exit 1
fi
requirements="$ROOT/backend/requirements.txt"
requirements_stamp="$ROOT/../.foxair-requirements-sha256"
expected="$(sha256sum "$requirements" | cut -d' ' -f1)"
actual="$(cat "$requirements_stamp" 2>/dev/null || true)"
if [[ "$actual" != "$expected" ]]; then
  echo "==> Python-Abhängigkeiten nur in eigener FoxAir-venv aktualisieren"
  "$venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir -r "$requirements"
  printf '%s\n' "$expected" > "$requirements_stamp"
fi

install -m 0644 "$stage/build-manifest.json" "$ROOT/build-manifest.json"
echo "==> Frontend austauschen"
if [[ -e "$backup" ]]; then rm -rf -- "$backup"; fi
if [[ -d "$dist" ]]; then
  chmod -R go-w "$dist"
  mv -- "$dist" "$backup"
fi
if ! mv -- "$stage" "$dist"; then
  if [[ -d "$backup" && ! -e "$dist" ]]; then mv -- "$backup" "$dist"; fi
  exit 1
fi
stage=""

if (( NO_RESTART == 0 )); then
  if systemctl list-unit-files foxair-web.service --no-legend 2>/dev/null | grep -q '^foxair-web.service'; then
    if (( SKIP_UNIT_SETUP == 0 )); then
      bash "$ROOT/scripts/install_stream_shutdown.sh"
    fi
    if (( was_active == 1 )); then
      echo "==> Nur foxair-web.service neu starten"
      systemctl start foxair-web.service
    else
      echo "==> FoxAir-Dienst inaktiv; kein automatischer Start"
    fi
  fi
fi
echo "OK: Code und Frontend von Commit $source_sha installiert"
