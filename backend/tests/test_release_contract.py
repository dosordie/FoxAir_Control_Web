import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
from unittest import TestCase, skipIf
from unittest.mock import patch
from backend import build_info, releases
from scripts import install_release as installer


def manifest():
    return {
        "schema": 1,
        "version": "0.1.0",
        "source_commit": "a" * 40,
        "frontend_source_commit": "a" * 40,
        "upstream_register_commit": "b" * 40,
        "build_channel": "release",
    }


class ReleaseContractTests(TestCase):
    def test_versions_compare_numerically_and_incomplete_releases_fail_closed(self):
        self.assertTrue(releases.newer("0.10.0", "0.9.9"))
        self.assertFalse(releases.newer("0.1.0-rc.1", "0.1.0"))
        with self.assertRaises(ValueError):
            releases.validate_ready(manifest())
        ready = {
            **manifest(),
            "ready": True,
            "archive_sha256": "c" * 64,
            "image_digest": "sha256:" + "d" * 64,
        }
        self.assertEqual(releases.validate_ready(ready)["version"], "0.1.0")
        with self.assertRaises(ValueError):
            build_info.validate({**manifest(), "frontend_source_commit": "c" * 40})

    def test_missing_marker_or_github_failure_never_offers_release(self):
        with (
            patch.object(releases, "_attempt", 0),
            patch.object(releases, "read_json", side_effect=OSError("offline")),
        ):
            self.assertIsNone(releases.latest(force=True))
        data = {"tag_name": "v0.1.0", "draft": False, "prerelease": False, "assets": []}
        with patch.object(releases, "read_json", return_value=data):
            self.assertIsNone(releases.latest(force=True))

    def test_build_identity_requires_matching_frontend_and_register_snapshot(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "frontend/dist").mkdir(parents=True)
            (root / "data").mkdir()
            (root / "VERSION").write_text("0.1.0")
            (root / "data/upstream.json").write_text(json.dumps({"ref": "b" * 40}))
            (root / "build-manifest.json").write_text(json.dumps(manifest()))
            frontend = root / "frontend/dist/build-manifest.json"
            frontend.write_text(json.dumps(manifest()))
            with patch.object(build_info, "ROOT", root):
                self.assertTrue(build_info.info()["build_consistent"])
                frontend.write_text(
                    json.dumps({**manifest(), "upstream_register_commit": "c" * 40})
                )
                self.assertFalse(build_info.info()["build_consistent"])

    def test_complete_release_keeps_only_fixed_repository_asset_urls(self):
        ready = {
            **manifest(),
            "ready": True,
            "archive_sha256": "c" * 64,
            "image_digest": "sha256:" + "d" * 64,
        }
        release = {
            "tag_name": "v0.1.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": name,
                    "browser_download_url": releases.asset_url("0.1.0", name),
                }
                for name in ("release-ready.json", "foxair-web-0.1.0.tar.gz")
            ],
        }
        with patch.object(releases, "read_json", side_effect=[release, ready]):
            self.assertEqual(releases.latest(force=True)["source_commit"], "a" * 40)
        release["assets"][0]["browser_download_url"] = "https://example.invalid/payload"
        with patch.object(releases, "read_json", return_value=release):
            self.assertIsNone(releases.latest(force=True))

    def test_archive_checksum_and_path_traversal_rejected_without_installing(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "payload.tar.gz"
            stage = root / "stage"
            stage.mkdir()
            with tarfile.open(archive, "w:gz") as tar:
                member = tarfile.TarInfo("../escape")
                member.size = 1
                tar.addfile(member, io.BytesIO(b"x"))
            checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                installer.extract(archive, stage, {"archive_sha256": "0" * 64})
            with self.assertRaises(ValueError):
                installer.extract(archive, stage, {"archive_sha256": checksum})
            self.assertFalse((root / "escape").exists())

    @skipIf(os.name == "nt", "POSIX deployment links are verified by Linux Actions")
    def test_migration_and_rollback_keep_matching_code_venv_and_untouched_state(self):
        with TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "app").mkdir()
            (base / "venv").mkdir()
            (base / "app/old").write_text("old")
            (base / "venv/dependency").write_text("old")
            state = base / "private-state"
            state.mkdir()
            (state / "users.json").write_text("preserve")
            target = base / "releases/new"
            (target / "venv").mkdir(parents=True)
            (target / "backend").mkdir()
            with (
                patch.object(installer, "BASE", base),
                patch.object(installer.subprocess, "run") as run,
            ):
                run.return_value.returncode = 1
                installer.deploy(target, manifest())
                self.assertEqual((base / "app").resolve(), target.resolve())
                self.assertEqual((base / "venv").resolve(), (target / "venv").resolve())
                installer.rollback()
                self.assertEqual((base / "app/old").read_text(), "old")
                self.assertEqual((base / "venv/dependency").read_text(), "old")
                self.assertEqual((state / "users.json").read_text(), "preserve")

    @skipIf(os.name == "nt", "POSIX links are verified in Linux Actions")
    def test_failed_health_restores_both_source_and_dependencies(self):
        with TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "app").mkdir()
            (base / "venv").mkdir()
            (base / "app/old").write_text("kept")
            (base / "venv/dependency").write_text("kept")
            target = base / "releases/new"
            (target / "venv").mkdir(parents=True)
            with (
                patch.object(installer, "BASE", base),
                patch.object(installer.subprocess, "run") as run,
                patch.object(
                    installer, "verify_running", side_effect=RuntimeError("unhealthy")
                ),
            ):
                run.return_value.returncode = 0
                with self.assertRaises(RuntimeError):
                    installer.deploy(target, manifest())
                self.assertEqual((base / "app/old").read_text(), "kept")
                self.assertEqual((base / "venv/dependency").read_text(), "kept")

    @skipIf(os.name == "nt", "POSIX links are verified in Linux Actions")
    def test_failed_link_replacement_restores_directory(self):
        with TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "app").mkdir()
            (base / "app/old").write_text("kept")
            target = base / "new"
            target.mkdir()
            with (
                patch.object(installer, "BASE", base),
                patch.object(
                    installer.os, "replace", side_effect=OSError("interrupted")
                ),
            ):
                with self.assertRaises(OSError):
                    installer.link("app", target)
                self.assertEqual((base / "app/old").read_text(), "kept")
