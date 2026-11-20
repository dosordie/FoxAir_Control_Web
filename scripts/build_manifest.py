"""Generate the identical deployment manifest for source and frontend."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.build_info import ROOT, product_version, validate, git_value


def build(source, channel):
    upstream = json.loads((ROOT / "data/upstream.json").read_text(encoding="utf-8"))[
        "ref"
    ]
    row = validate(
        {
            "schema": 1,
            "version": product_version(),
            "source_commit": source,
            "frontend_source_commit": source,
            "upstream_register_commit": upstream,
            "build_channel": channel,
        }
    )
    for path in (
        ROOT / "build-manifest.json",
        ROOT / "frontend/dist/build-manifest.json",
    ):
        path.write_text(
            json.dumps(row, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    (ROOT / "frontend/dist/.build-source-sha").write_text(
        source + "\n", encoding="ascii"
    )
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=git_value("rev-parse", "HEAD"))
    parser.add_argument(
        "--channel", choices=("work", "release", "preview"), required=True
    )
    args = parser.parse_args()
    build(args.source, args.channel)
