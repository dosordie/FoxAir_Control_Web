"""Create immutable Linux/source+frontend bundle and shared release-ready metadata."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.build_info import ROOT, validate, product_version, git_value
from backend.releases import validate_ready


def package(digest):
    manifest = validate(json.loads((ROOT / "build-manifest.json").read_text()))
    if manifest["build_channel"] != "release" or manifest["source_commit"] != git_value(
        "rev-parse", "HEAD"
    ):
        raise ValueError("Only exact release source can be packaged")
    output = ROOT / "release-assets"
    output.mkdir(exist_ok=True)
    archive = output / f"foxair-web-{product_version()}.tar.gz"
    with tempfile.TemporaryDirectory() as folder:
        stage = Path(folder) / "source"
        stage.mkdir()
        source_tar = Path(folder) / "source.tar"
        with source_tar.open("wb") as handle:
            subprocess.run(
                ["git", "archive", "HEAD"], cwd=ROOT, stdout=handle, check=True
            )
        with tarfile.open(source_tar) as tar:
            tar.extractall(stage, filter="data")
        shutil.copytree(ROOT / "frontend/dist", stage / "frontend/dist")
        shutil.copyfile(ROOT / "build-manifest.json", stage / "build-manifest.json")
        with tarfile.open(archive, "w:gz") as tar:
            for path in stage.iterdir():
                tar.add(path, arcname=path.name)
    with archive.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    ready = validate_ready(
        {**manifest, "ready": True, "archive_sha256": checksum, "image_digest": digest}
    )
    (output / "release-ready.json").write_text(json.dumps(ready, indent=2) + "\n")
    (output / "SHA256SUMS").write_text(checksum + "  " + archive.name + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--digest", required=True)
    package(parser.parse_args().digest)
