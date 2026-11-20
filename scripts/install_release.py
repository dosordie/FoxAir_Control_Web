"""Root-only release staging and reversible app/venv handover; no state migration."""

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.releases import latest, validate_ready, newer
from backend.build_info import validate

BASE = Path(os.environ.get("FOXAIR_INSTALL_ROOT", "/opt/foxair-web"))


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def extract(archive, stage, ready):
    with archive.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != ready["archive_sha256"]:
        raise ValueError("Release checksum mismatch")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if len(members) > 20000 or sum(item.size for item in members) > 500_000_000:
            raise ValueError("Release too large")
        for item in members:
            target = stage / item.name
            if not target.resolve().is_relative_to(stage.resolve()) or not (
                item.isdir() or item.isfile()
            ):
                raise ValueError("Unsafe archive member")
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o755)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(item) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o755 if item.mode & 0o111 else 0o644)
    root = validate(json.loads((stage / "build-manifest.json").read_text()))
    frontend = validate(
        json.loads((stage / "frontend/dist/build-manifest.json").read_text())
    )
    if (
        root != frontend
        or root["build_channel"] != "release"
        or any(root[key] != ready[key] for key in root)
    ):
        raise ValueError("Release manifest mismatch")
    if (stage / "frontend/dist/.build-source-sha").read_text().strip() != ready[
        "source_commit"
    ] or not (stage / "frontend/dist/index.html").is_file():
        raise ValueError("Missing or wrong frontend")
    if (stage / "VERSION").read_text().strip() != ready["version"]:
        raise ValueError("Wrong source version")


def link(name, target):
    path = BASE / name
    if (path.exists() or path.is_symlink()) and not path.resolve().is_relative_to(
        BASE.resolve()
    ):
        raise ValueError("Existing installation points outside install root")
    temp = BASE / ("." + name + ".next")
    temp.unlink(missing_ok=True)
    temp.symlink_to(target, target_is_directory=True)
    moved = False
    if path.is_symlink():
        previous = path.resolve()
    elif path.exists():
        previous = BASE / f"{name}.legacy-{time.time_ns()}"
        path.rename(previous)
        moved = True
    else:
        previous = None
    try:
        os.replace(temp, path)
    except BaseException:
        if moved and not path.exists():
            previous.rename(path)
        temp.unlink(missing_ok=True)
        raise
    return previous


def health_url():
    text = subprocess.check_output(
        ["systemctl", "show", "foxair-web.service", "--property=ExecStart", "--value"],
        text=True,
    )
    match = re.search(r"--host\s+([0-9a-fA-F:.]+)", text)
    host = str(ipaddress.ip_address(match.group(1))) if match else "127.0.0.1"
    host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    return f"http://{'[' + host + ']' if ':' in host else host}:8081/api/health"


def verify_running(ready):
    url = health_url()
    for _ in range(30):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                body = json.load(response)
            if (
                body.get("ok")
                and body.get("build", {}).get("source_commit") == ready["source_commit"]
                and body["build"].get("build_consistent")
            ):
                return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(1)
    raise RuntimeError("New release failed its health/version check")


def deploy(target, ready):
    environment = subprocess.run(
        [
            "systemctl",
            "show",
            "foxair-web.service",
            "--property=EnvironmentFiles",
            "--value",
        ],
        capture_output=True,
        text=True,
    )
    if str(BASE / "app") + "/" in str(environment.stdout):
        raise RuntimeError(
            "App-local EnvironmentFile must be moved outside the release directory before migration"
        )
    active = (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "foxair-web.service"]
        ).returncode
        == 0
    )
    previous = {}
    if active:
        run("systemctl", "stop", "foxair-web.service")
    try:
        previous["venv"] = link("venv", BASE / "app/venv")
        previous["app"] = link("app", target)
        if (
            previous["app"]
            and previous["venv"]
            and not (previous["app"] / "venv").exists()
        ):
            (previous["app"] / "venv").symlink_to(
                previous["venv"], target_is_directory=True
            )
        if active:
            run("systemctl", "start", "foxair-web.service")
            verify_running(ready)
        record = {
            "previous": {key: str(value) for key, value in previous.items() if value},
            "active": active,
        }
        (BASE / "release-rollback.json").write_text(json.dumps(record))
        (BASE / "release-rollback.json").chmod(0o600)
    except BaseException:
        if active:
            subprocess.run(["systemctl", "stop", "foxair-web.service"])
        if previous.get("app"):
            if previous.get("venv") and not (previous["app"] / "venv").exists():
                (previous["app"] / "venv").symlink_to(
                    previous["venv"], target_is_directory=True
                )
            link("app", previous["app"])
            link("venv", BASE / "app/venv")
        elif previous.get("venv"):
            link("venv", previous["venv"])
        if active:
            run("systemctl", "start", "foxair-web.service")
        raise


def rollback():
    record = json.loads((BASE / "release-rollback.json").read_text())
    targets = {key: Path(value) for key, value in record["previous"].items()}
    if set(targets) != {"app", "venv"} or any(
        not path.is_dir() or not path.resolve().is_relative_to(BASE.resolve())
        for path in targets.values()
    ):
        raise ValueError("No valid local rollback")
    active = (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "foxair-web.service"]
        ).returncode
        == 0
    )
    if active:
        run("systemctl", "stop", "foxair-web.service")
    link("venv", BASE / "app/venv")
    link("app", targets["app"])
    if active:
        run("systemctl", "start", "foxair-web.service")


def install():
    ready = latest(force=True)
    if ready is None:
        raise RuntimeError("No complete approved stable release is available")
    validate_ready(ready)
    installed_file = BASE / "app/build-manifest.json"
    if installed_file.is_file():
        installed = validate(json.loads(installed_file.read_text()))
        if newer(installed["version"], ready["version"]):
            raise RuntimeError(
                "Automatic downgrade is forbidden; use explicit local rollback"
            )
        if (
            installed["build_channel"] == "release"
            and installed["source_commit"] == ready["source_commit"]
        ):
            print("Release already installed; rollback reference retained")
            return
    releases = BASE / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    releases.chmod(0o755)
    target = releases / (ready["version"] + "-" + ready["source_commit"])
    if target.exists():
        if not (target / "install-ready.json").is_file():
            if (BASE / "app").resolve() == target.resolve():
                raise RuntimeError("Active release is incomplete; recover manually")
            target.rename(target.with_name(target.name + f".failed-{time.time_ns()}"))
        elif json.loads((target / "install-ready.json").read_text()) != ready:
            raise RuntimeError(
                "Immutable version already exists with different metadata"
            )
    if not target.exists():
        with tempfile.TemporaryDirectory(
            prefix=".release-stage-", dir=releases
        ) as temp:
            stage = Path(temp)
            archive = stage / "download.tar.gz"
            with (
                urllib.request.urlopen(ready["archive_url"], timeout=30) as response,
                archive.open("wb") as output,
            ):
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 200_000_000:
                        raise ValueError("Release download too large")
                    output.write(chunk)
            source = stage / "source"
            source.mkdir(mode=0o755)
            extract(archive, source, ready)
            os.replace(source, target)
        run(sys.executable, "-m", "venv", str(target / "venv"))
        python = str(target / "venv/bin/python")
        run(
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "-r",
            str(target / "backend/requirements.txt"),
        )
        run(
            python,
            "-c",
            "from backend.main import app; from backend.build_info import info; assert info()['build_consistent']",
            cwd=target,
        )
        (target / "install-ready.json").write_text(json.dumps(ready, sort_keys=True))
    deploy(target, ready)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise SystemExit("Root required")
    rollback() if args.rollback else install()
