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
REMOTE_API = "https://api.github.com/repos/dosordie/FoxAir_Control_Web/branches/work"
REMOTE_BUILD = "https://raw.githubusercontent.com/dosordie/FoxAir_Control_Web/web-dist-work/.build-source-sha"
_last_remote_attempt = 0.0
_last_remote_sha: str | None = None
_last_remote_build_attempt = 0.0
_last_remote_build_sha: str | None = None


def _cmd(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args, text=True, capture_output=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _current_sha() -> str | None:
    result = _cmd("git", "-C", str(ROOT), "rev-parse", "HEAD")
    sha = result.stdout.strip() if result and result.returncode == 0 else ""
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def _deployed_sha() -> str | None:
    """Compiled UI revision, which may lag the working tree after a CI delay."""
    try:
        sha = (
            (ROOT / "frontend" / "dist" / ".build-source-sha")
            .read_text(encoding="utf-8")
            .strip()
        )
    except OSError:
        return None
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def _remote_sha() -> str | None:
    global _last_remote_attempt, _last_remote_sha
    now = time.monotonic()
    if _last_remote_attempt and now - _last_remote_attempt < 30:
        return _last_remote_sha
    _last_remote_attempt = now
    try:
        request = urllib.request.Request(
            REMOTE_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "FoxAir-Control-Web-Updater/1",
            },
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
    if _last_remote_build_attempt and now - _last_remote_build_attempt < 30:
        return _last_remote_build_sha
    _last_remote_build_attempt = now
    try:
        request = urllib.request.Request(
            REMOTE_BUILD,
            headers={"User-Agent": "FoxAir-Control-Web-Updater/1"},
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            sha = response.read(200).decode("ascii").strip()
        _last_remote_build_sha = sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None
    except (OSError, ValueError, UnicodeError, urllib.error.URLError):
        _last_remote_build_sha = None
    return _last_remote_build_sha


def _status_unit(unit: str) -> dict[str, str]:
    result = _cmd(
        "systemctl",
        "show",
        unit,
        "--property=LoadState,ActiveState,Result,ExecMainStatus",
    )
    if not result or result.returncode:
        return {}
    return dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )


def status() -> dict[str, Any]:
    from backend.build_info import info
    from backend.releases import latest, newer

    build = info()
    container = os.getenv("FOXAIR_CONTAINER") == "1"
    mode = (
        "container"
        if container
        else "work"
        if build["build_channel"] == "work"
        else "release"
    )
    deployed = _deployed_sha()
    watcher = _status_unit(PATH_UNIT) if mode == "release" else {}
    service = _status_unit(SERVICE) if mode == "release" else {}
    if mode == "container":
        from backend.docker_updates import latest as docker_latest

        release = docker_latest()
        available = bool(
            release
            and (
                newer(release["version"], build["version"])
                or (
                    release["version"] == build["version"]
                    and build.get("source_commit") is not None
                    and build["source_commit"] != release["source_commit"]
                )
            )
        )
        check = "checked" if release else "unavailable"
        if release:
            release = {
                **release,
                "notes_url": "https://github.com/dosordie/FoxAir_Control_Web/pkgs/container/foxair-control-web",
            }
    elif mode == "work":
        head = _remote_sha()
        artifact = _remote_build_sha()
        release = (
            {
                "version": "work · " + head[:10],
                "source_commit": head,
                "frontend_source_commit": artifact,
                "notes_url": "https://github.com/dosordie/FoxAir_Control_Web/tree/work",
            }
            if head
            else None
        )
        available = bool(
            head and head == artifact and head != build.get("source_commit")
        )
        check = (
            "unavailable"
            if not head or not artifact
            else "checked"
            if head == artifact
            else "building"
        )
    else:
        release = latest()
        available = bool(
            release
            and (
                newer(release["version"], build["version"])
                or (
                    build["build_channel"] != "release"
                    and release["version"] == build["version"]
                )
            )
        )
        check = "checked" if release else "unavailable"
    return {
        "installed": watcher.get("LoadState") == "loaded"
        and watcher.get("ActiveState") == "active",
        "current": build.get("source_commit"),
        "deployed": deployed,
        "remote": release.get("source_commit") if release else None,
        "remote_build": release.get("frontend_source_commit") if release else None,
        "build_ready": check == "checked",
        "check_status": check,
        "update_available": available,
        "pending": TRIGGER.exists() if mode == "release" else False,
        "running": service.get("ActiveState") in ("active", "activating"),
        "last_result": service.get("Result"),
        "version": build["display_version"],
        "available_version": release.get("version") if release else None,
        "channel": build["build_channel"],
        "update_mode": mode,
        "notes_url": release.get("notes_url") if release else None,
        "build_consistent": build["build_consistent"],
    }


def request_update() -> dict[str, Any]:
    from backend.build_info import info
    from backend.releases import latest, newer

    if os.getenv("FOXAIR_CONTAINER") == "1":
        raise RuntimeError("Container über Compose oder Portainer aktualisieren")
    if info()["build_channel"] == "work":
        raise RuntimeError("Test-VM manuell mit scripts/update-work.sh aktualisieren")
    candidate = latest()
    installed = info()
    if candidate is None:
        raise RuntimeError("Kein vollständiges freigegebenes Release verfügbar")
    if not newer(candidate["version"], installed["version"]) and not (
        candidate["version"] == installed["version"]
        and installed["build_channel"] != "release"
    ):
        raise RuntimeError("Kein neueres freigegebenes Release verfügbar")
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
