#!/usr/bin/env python3
"""Validate a single FoxAir Web version across source files and release tags.

Read-only; safe to execute in PRs, Actions, or local checkouts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"0|[1-9][0-9]*")
VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def version() -> str:
    v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not VERSION_RE.fullmatch(v):
        raise SystemExit(f"Invalid VERSION: {v!r}; use MAJOR.MINOR.PATCH")
    return v


def check(tag: str | None = None) -> str:
    v = version()
    pkg = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
    errors = []
    for name, found in (
        ("frontend/package.json", pkg.get("version")),
        ("frontend/package-lock.json", lock.get("version")),
        ("frontend/package-lock.json packages root", lock.get("packages", {}).get("", {}).get("version")),
    ):
        if found != v:
            errors.append(f"{name}: {found!r} != {v!r}")
    fastapi = re.search(r'\bapp\s*=\s*FastAPI\([^\n]*\bversion="([^"]+)"', main)
    if not fastapi or fastapi.group(1) != v:
        errors.append(f"backend/main.py FastAPI version != {v!r}")
    if tag is not None and tag != "v" + v:
        errors.append(f"Git release tag {tag!r} != expected {'v' + v!r}")
    if errors:
        raise SystemExit("Release version check failed:\n" + "\n".join(errors))
    print(f"OK: FoxAir Control Web {v} (tag {tag or 'not supplied'})")
    return v


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="Expected GitHub tag, e.g. v0.1.0")
    args = parser.parse_args()
    check(args.tag)
