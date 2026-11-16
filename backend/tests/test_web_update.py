"""Restricted updater: filesystem trigger only, no arbitrary shell execution."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import web_update


class WebUpdateTests(unittest.TestCase):
    def test_request_creates_only_fixed_trigger_once(self):
        with TemporaryDirectory() as tmp:
            flag = Path(tmp) / "update-request"
            def unit(unit):
                return {"LoadState": "loaded", "ActiveState":
                        "active" if unit == web_update.PATH_UNIT else "inactive"}
            with patch.object(web_update, "TRIGGER", flag), \
                    patch.object(web_update, "_status_unit", side_effect=unit):
                result = web_update.request_update()
                self.assertTrue(result["requested"])
                self.assertTrue(flag.is_file())
                self.assertEqual(flag.read_bytes(), b"")
                with self.assertRaises(RuntimeError):
                    web_update.request_update()

    def test_disabled_watcher_refuses_request(self):
        with TemporaryDirectory() as tmp:
            flag = Path(tmp) / "update-request"
            with patch.object(web_update, "TRIGGER", flag), \
                    patch.object(web_update, "_status_unit",
                                 return_value={"LoadState": "not-found", "ActiveState": "inactive"}):
                with self.assertRaises(RuntimeError):
                    web_update.request_update()
                self.assertFalse(flag.exists())

    def test_version_status_detects_incomplete_deployment(self):
        head = "a" * 40
        older = "b" * 40
        with patch.object(web_update, "_current_sha", return_value=head), \
                patch.object(web_update, "_remote_sha", return_value=head), \
                patch.object(web_update, "_deployed_sha", return_value=older), \
                patch.object(web_update, "_status_unit", return_value={
                    "LoadState": "loaded", "ActiveState": "inactive", "Result": "success"
                }):
            result = web_update.status()
        self.assertTrue(result["update_available"])
        self.assertEqual(result["current"], head)
        self.assertEqual(result["deployed"], older)


if __name__ == "__main__":
    unittest.main()
