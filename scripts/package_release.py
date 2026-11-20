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


def package(digest=None, image_id=None):
    manifest = validate(json.loads((ROOT / "build-manifest.json").read_text()))
    channel = "prerelease" if image_id else "release"
    if manifest["build_channel"] != channel or manifest["source_commit"] != git_value(
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
    ready = {**manifest, "ready": True, "archive_sha256": checksum}
    checksums = [checksum + "  " + archive.name]
    if image_id:
        from re import fullmatch

        if not fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise ValueError("Invalid Docker image ID")
        docker_archive = output / f"foxair-web-docker-{product_version()}-amd64.tar.gz"
        with docker_archive.open("rb") as handle:
            docker_checksum = hashlib.file_digest(handle, "sha256").hexdigest()
        ready.update(image_id=image_id, docker_archive_sha256=docker_checksum)
        checksums.append(docker_checksum + "  " + docker_archive.name)
    else:
        ready["image_digest"] = digest
        validate_ready(ready)
    (output / "release-ready.json").write_text(json.dumps(ready, indent=2) + "\n")
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    image = parser.add_mutually_exclusive_group(required=True)
    image.add_argument("--digest")
    image.add_argument("--image-id")
    args = parser.parse_args()
    package(args.digest, args.image_id)
