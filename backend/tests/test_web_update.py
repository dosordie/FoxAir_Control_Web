"""Restricted updater: filesystem trigger only, no arbitrary shell execution."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import web_update


class WebUpdateTests(unittest.TestCase):
    def setUp(self):
        for item in (
            patch(
                "backend.build_info.info",
                return_value={
                    "version": "0.1.0",
                    "display_version": "0.1.0 (legacy/main)",
                    "source_commit": "a" * 40,
                    "build_channel": "legacy/main",
                    "build_consistent": False,
                },
            ),
            patch(
                "backend.releases.latest",
                return_value={
                    "version": "0.1.0",
                    "source_commit": "a" * 40,
                    "frontend_source_commit": "a" * 40,
                    "notes_url": "https://github.com/dosordie/FoxAir_Control_Web/releases/tag/v0.1.0",
                },
            ),
        ):
            item.start()
            self.addCleanup(item.stop)

    def test_container_never_invokes_systemd_or_creates_trigger(self):
        with (
            patch.dict("os.environ", {"FOXAIR_CONTAINER": "1"}),
            patch.object(web_update, "_status_unit") as unit,
        ):
            self.assertEqual(web_update.status()["update_mode"], "container")
            with self.assertRaises(RuntimeError):
                web_update.request_update()
            unit.assert_not_called()

    def test_work_mode_never_invokes_systemd_or_requests_production_update(self):
        with (
            patch(
                "backend.build_info.info",
                return_value={
                    "version": "0.1.0",
                    "source_commit": "a" * 40,
                    "display_version": "0.1.0-dev+aaaaaaaaaa",
                    "build_channel": "work",
                    "build_consistent": True,
                },
            ),
            patch.object(web_update, "_status_unit") as unit,
        ):
            self.assertEqual(web_update.status()["update_mode"], "work")
            with self.assertRaises(RuntimeError):
                web_update.request_update()
            unit.assert_not_called()

    def test_request_creates_only_fixed_trigger_once(self):
        with TemporaryDirectory() as tmp:
            flag = Path(tmp) / "update-request"

            def unit(unit):
                return {
                    "LoadState": "loaded",
                    "ActiveState": "active"
                    if unit == web_update.PATH_UNIT
                    else "inactive",
                }

            with (
                patch.object(web_update, "TRIGGER", flag),
                patch.object(web_update, "_status_unit", side_effect=unit),
            ):
                result = web_update.request_update()
                self.assertTrue(result["requested"])
                self.assertTrue(flag.is_file())
                self.assertEqual(flag.read_bytes(), b"")
                with self.assertRaises(RuntimeError):
                    web_update.request_update()

    def test_disabled_watcher_refuses_request(self):
        with TemporaryDirectory() as tmp:
            flag = Path(tmp) / "update-request"
            with (
                patch.object(web_update, "TRIGGER", flag),
                patch.object(
                    web_update,
                    "_status_unit",
                    return_value={"LoadState": "not-found", "ActiveState": "inactive"},
                ),
            ):
                with self.assertRaises(RuntimeError):
                    web_update.request_update()
                self.assertFalse(flag.exists())

    def test_version_status_detects_incomplete_deployment(self):
        head = "a" * 40
        older = "b" * 40
        with (
            patch.object(web_update, "_current_sha", return_value=head),
            patch.object(web_update, "_remote_sha", return_value=head),
            patch.object(web_update, "_deployed_sha", return_value=older),
            patch.object(web_update, "_remote_build_sha", return_value=head),
            patch.object(
                web_update,
                "_status_unit",
                return_value={
                    "LoadState": "loaded",
                    "ActiveState": "inactive",
                    "Result": "success",
                },
            ),
        ):
            result = web_update.status()
        self.assertTrue(result["update_available"])
        self.assertEqual(result["current"], head)
        self.assertEqual(result["deployed"], older)


if __name__ == "__main__":
    unittest.main()
