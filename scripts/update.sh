#!/usr/bin/env bash
# Production updates use complete immutable releases only; no git pull main.
set -euo pipefail
if (( EUID != 0 )); then echo "Bitte als root ausführen." >&2; exit 1; fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(git -C "$ROOT" branch --show-current 2>/dev/null || true)" == work ]]; then
  echo "Test-VM: bash scripts/update-work.sh verwenden; kein produktiver Kanalwechsel." >&2
  exit 1
fi
exec /opt/foxair-web/venv/bin/python "$ROOT/scripts/install_release.py" "$@"
