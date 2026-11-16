#!/usr/bin/env python3
"""Refresh ONLY register JSON snapshots from a reviewed FoxAir_Control commit.

Usage: python scripts/sync_registers.py --ref <reviewed_upstream_commit_sha>
Review git diff before merging. Never replace the runtime mapping via a live,
unverified 'main' fetch. Stdlib only.
"""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "foxair_phnix_registers.json",
    "foxair_phnix_display_registers.json",
    "foxair_phnix_knowledge.json",
)
UPSTREAM = "dosordie/FoxAir_Control"


def download(ref: str, name: str) -> str:
    url = f"https://raw.githubusercontent.com/{UPSTREAM}/{ref}/data/{name}"
    req = Request(url, headers={"User-Agent": "FoxAir-Control-Web-register-sync"})
    with urlopen(req, timeout=15) as res:
        return res.read().decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True, help="40-character reviewed upstream commit SHA")
    args = parser.parse_args()
    ref = args.ref.strip()
    if len(ref) != 40 or any(ch not in "0123456789abcdef" for ch in ref.lower()):
        parser.error("--ref must be a 40-character commit SHA")
    target = ROOT / "data"
    target.mkdir(exist_ok=True)
    downloads = {}
    for name in FILES:
        content = download(ref, name)
        doc = json.loads(content)
        if not isinstance(doc, dict) or len(doc) < 20:
            raise ValueError("Unplausible Registerdatei: " + name)
        downloads[name] = content
    for name, content in downloads.items():
        (target / name).write_text(content, encoding="utf-8")
        print(name, len(content), "bytes")
    (target / "upstream.json").write_text(
        json.dumps({"repository": UPSTREAM, "ref": ref, "managed_files": list(FILES)}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
