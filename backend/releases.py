"""Only complete stable releases from this repository may be offered for updates."""

import json
import re
import time
import urllib.request
import urllib.error
from backend.build_info import SEMVER, SHA, validate

REPO = "dosordie/FoxAir_Control_Web"
API = "https://api.github.com/repos/" + REPO + "/releases/latest"
_cache = None
_attempt = 0.0


def asset_url(version, name):
    if not SEMVER.fullmatch(version) or name not in (
        f"foxair-web-{version}.tar.gz",
        "release-ready.json",
    ):
        raise ValueError("Invalid release asset")
    return f"https://github.com/{REPO}/releases/download/v{version}/{name}"


def validate_ready(row):
    validate(row)
    if row["build_channel"] != "release" or row.get("ready") is not True:
        raise ValueError("Release not ready")
    if not re.fullmatch(
        r"sha256:[0-9a-f]{64}", str(row.get("image_digest", ""))
    ) or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("archive_sha256", ""))):
        raise ValueError("Release lacks immutable artifacts")
    return row


def read_json(url, limit=262144):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "FoxAir-Web-Releases/1",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Release metadata too large")
    return json.loads(data)


def latest(force=False):
    global _cache, _attempt
    now = time.monotonic()
    if not force and _attempt and now - _attempt < 60:
        return _cache
    _attempt = now
    try:
        release = read_json(API)
        tag = release.get("tag_name", "")
        if (
            release.get("draft")
            or release.get("prerelease")
            or not tag.startswith("v")
            or not SEMVER.fullmatch(tag[1:])
        ):
            raise ValueError("Not stable")
        version = tag[1:]
        assets = {item["name"]: item for item in release.get("assets", [])}
        for name in ("release-ready.json", f"foxair-web-{version}.tar.gz"):
            if assets[name]["browser_download_url"] != asset_url(version, name):
                raise ValueError("Unexpected asset URL")
        row = validate_ready(read_json(asset_url(version, "release-ready.json")))
        if row["version"] != version:
            raise ValueError("Version mismatch")
        _cache = {
            **row,
            "tag": tag,
            "archive_url": asset_url(version, f"foxair-web-{version}.tar.gz"),
            "notes_url": f"https://github.com/{REPO}/releases/tag/{tag}",
        }
    except (OSError, ValueError, TypeError, KeyError):
        _cache = None
    return _cache


def newer(candidate, installed):
    if not SEMVER.fullmatch(candidate) or not SEMVER.fullmatch(installed):
        return False
    return tuple(map(int, candidate.split("."))) > tuple(map(int, installed.split(".")))


def assert_new_stable(version):
    try:
        current = read_json(API)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return
        raise
    tag = current.get("tag_name", "")
    if not tag.startswith("v") or not newer(version, tag[1:]):
        raise ValueError("A newer or equal stable release already exists")
