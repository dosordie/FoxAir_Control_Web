"""Restricted on-demand Git updater state for the FoxAir-only systemd path unit.

The unprivileged web server never executes git, pip, shell, sudo, or systemctl
start. After an authenticated HTTPS POST it only creates one fixed trigger
file. A separately installed root-owned systemd path/service runs the exact
root-owned update.sh script, with no caller-supplied commands or arguments.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

from backend.cloud_config import STATE_DIR

ROOT = Path(__file__).resolve().parents[1]
TRIGGER = STATE_DIR / "update-request"
SERVICE = "foxair-web-update.service"
PATH_UNIT = "foxair-web-update.path"
REMOTE_API = "https://api.github.com/repos/dosordie/FoxAir_Control_Web/branches/main"
REMOTE_BUILD = "https://raw.githubusercontent.com/dosordie/FoxAir_Control_Web/web-dist/.build-source-sha"
_last_remote_attempt = 0.0
_last_remote_sha: str | None = None
_last_remote_build_attempt = 0.0
_last_remote_build_sha: str | None = None


def _cmd(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _current_sha() -> str | None:
    result = _cmd("git", "-C", str(ROOT), "rev-parse", "HEAD")
    sha = result.stdout.strip() if result and result.returncode == 0 else ""
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def _deployed_sha() -> str | None:
    """Compiled UI revision, which may lag the working tree after a CI delay."""
    try:
        sha = (ROOT / "frontend" / "dist" / ".build-source-sha").read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        return None
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def _remote_sha() -> str | None:
    global _last_remote_attempt, _last_remote_sha
    now = time.monotonic()
    if _last_remote_attempt and now - _last_remote_attempt < 90:
        return _last_remote_sha
    _last_remote_attempt = now
    try:
        request = urllib.request.Request(
            REMOTE_API, headers={"Accept": "application/vnd.github+json",
                                 "User-Agent": "FoxAir-Control-Web-Updater/1"},
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            body = json.loads(response.read(32_768))
        sha = str(body.get("commit", {}).get("sha") or "")
        _last_remote_sha = sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None
    except (OSError, ValueError, TypeError, urllib.error.URLError):
        _last_remote_sha = None
    return _last_remote_sha


def _remote_build_sha() -> str | None:
    global _last_remote_build_attempt, _last_remote_build_sha
    now = time.monotonic()
    if _last_remote_build_attempt and now - _last_remote_build_attempt < 90:
        return _last_remote_build_sha
    _last_remote_build_attempt = now
    try:
        request = urllib.request.Request(
            REMOTE_BUILD, headers={"User-Agent": "FoxAir-Control-Web-Updater/1"},
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            sha = response.read(200).decode("ascii").strip()
        _last_remote_build_sha = sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None
    except (OSError, ValueError, UnicodeError, urllib.error.URLError):
        _last_remote_build_sha = None
    return _last_remote_build_sha


def _status_unit(unit: str) -> dict[str, str]:
    result = _cmd("systemctl", "show", unit,
                  "--property=LoadState,ActiveState,Result,ExecMainStatus")
    if not result or result.returncode:
        return {}
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def status() -> dict[str, Any]:
    current = _current_sha()
    remote = _remote_sha()
    deployed = _deployed_sha()
    remote_build = _remote_build_sha()
    watcher = _status_unit(PATH_UNIT)
    service = _status_unit(SERVICE)
    installed = watcher.get("LoadState") == "loaded" and watcher.get("ActiveState") == "active"
    running = service.get("ActiveState") in ("activating", "active")
    return {
        "installed": installed,
        "current": current,
        "deployed": deployed,
        "remote": remote,
        "remote_build": remote_build,
        "build_ready": bool(remote and remote_build and remote == remote_build),
        "update_available": bool(current and remote and current != remote) or
                            bool(current and deployed and current != deployed),
        "pending": TRIGGER.exists(),
        "running": running,
        "last_result": service.get("Result") if service.get("LoadState") == "loaded" else None,
    }


def request_update() -> dict[str, Any]:
    watcher = _status_unit(PATH_UNIT)
    if watcher.get("LoadState") != "loaded" or watcher.get("ActiveState") != "active":
        raise RuntimeError("Update-Hilfsdienst noch nicht eingerichtet")
    service = _status_unit(SERVICE)
    if service.get("ActiveState") in ("active", "activating"):
        raise RuntimeError("Update läuft bereits")
    # The file path and contents are constant. O_EXCL + O_NOFOLLOW avoids
    # replacing anything; trigger directory is writable by FoxAir only.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(TRIGGER, flags, 0o600)
        os.close(fd)
    except FileExistsError:
        raise RuntimeError("Update-Anforderung liegt bereits vor") from None
    except OSError:
        raise RuntimeError("Update-Anforderung konnte nicht übergeben werden") from None
    return {"requested": True}
