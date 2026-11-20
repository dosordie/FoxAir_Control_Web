"""Shared, non-secret build identity for Linux and container distributions."""

import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}")
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def product_version():
    return (
        (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        if (ROOT / "VERSION").is_file()
        else "0.1.0"
    )


def validate(row):
    if (
        not isinstance(row, dict)
        or row.get("schema") != 1
        or not SEMVER.fullmatch(str(row.get("version", "")))
    ):
        raise ValueError("Invalid build version")
    if (
        not SHA.fullmatch(str(row.get("source_commit", "")))
        or row.get("frontend_source_commit") != row["source_commit"]
    ):
        raise ValueError("Frontend/backend source mismatch")
    if not SHA.fullmatch(str(row.get("upstream_register_commit", ""))) or row.get(
        "build_channel"
    ) not in ("work", "release", "preview"):
        raise ValueError("Invalid build identity")
    return row


def git_value(*args):
    # The service deliberately reads a root-owned checkout. Trust only this fixed
    # application directory for read-only identity commands; never global wildcards.
    try:
        return subprocess.run(
            ["git", "-c", "safe.directory=" + str(ROOT), "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def info():
    try:
        row = validate(
            json.loads((ROOT / "build-manifest.json").read_text(encoding="utf-8"))
        )
        frontend = validate(
            json.loads(
                (ROOT / "frontend/dist/build-manifest.json").read_text(encoding="utf-8")
            )
        )
        consistent = (
            row == frontend
            and row["version"] == product_version()
            and row["upstream_register_commit"]
            == json.loads((ROOT / "data/upstream.json").read_text())["ref"]
        )
        if (ROOT / ".git").exists():
            consistent = (
                consistent and git_value("rev-parse", "HEAD") == row["source_commit"]
            )
        version = (
            row["version"]
            if row["build_channel"] == "release"
            else row["version"] + "-dev+" + row["source_commit"][:10]
        )
        return {**row, "display_version": version, "build_consistent": consistent}
    except (OSError, ValueError, TypeError):
        sha = git_value("rev-parse", "HEAD")
        channel = (
            "work" if git_value("branch", "--show-current") == "work" else "legacy/main"
        )
        return {
            "version": product_version(),
            "source_commit": sha if SHA.fullmatch(sha) else None,
            "build_channel": channel,
            "display_version": product_version()
            + ("-dev+" + sha[:10] if channel == "work" else " (legacy/main)"),
            "build_consistent": False,
        }
