"""No-network full scan tests with reviewed code kinds and unsupported bisection."""
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory, Mock

from backend import cloud_state
from backend.cloud_read import UnsupportedCloudCode


class FullCatalogScanTests(unittest.TestCase):
    def test_all_known_candidates_tried_without_losing_valid_results(self):
        account = ("not-real-user", "not-real-password", "not-real-device")
        candidates = [
            {"code": "T04", "name": "Außentemperatur", "kind": "live",
             "group": "T", "register": 2048, "confidence": "confirmed", "unit": "°C"},
            {"code": "UNKNOWN", "name": "Unknown", "kind": "other",
             "group": "CLOUD", "register": None, "confidence": "", "unit": ""},
        ]
        calls = []
        reader = Mock()

        def read_codes(codes):
            calls.append(codes)
            if "UNKNOWN" in codes:
                raise UnsupportedCloudCode("Cloud-Code von API nicht unterstützt")
            return {"T04": {"value": -2.1, "unit": "°C"}}
        reader.read_codes.side_effect = read_codes

        with patch("backend.cloud_state._account", return_value=account), \
                patch("backend.cloud_state.catalog", return_value=candidates), \
                patch("backend.cloud_state._reader", return_value=reader):
            cloud_state._reset_if_changed()
            cloud_state._scan_worker(account, candidates)
            values = cloud_state.value_rows()

        self.assertEqual(values["status"], "complete")
        self.assertEqual(values["supported"], 1)
        known = next(row for row in values["items"] if row["code"] == "T04")
        unknown = next(row for row in values["items"] if row["code"] == "UNKNOWN")
        self.assertEqual(known["value"], -2.1)
        self.assertIsNone(unknown["value"])
        self.assertGreaterEqual(len(calls), 3)

    def test_persisted_cache_restores_last_values_as_stale_without_identifiers(self):
        account = ("sample@example.invalid", "secret-token-not-committed", "device-test-01")
        with TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "last.json"
            with patch.object(cloud_state, "_CACHE_FILE", cache_path), \
                    patch("backend.cloud_state._account", return_value=account):
                with cloud_state._LOCK:
                    cloud_state._SOURCE = None
                    cloud_state._ROWS.clear()
                cloud_state.merge({"T01": {"value": 39.4, "unit": "°C"}}, source=account)
                self.assertTrue(cache_path.is_file())
                raw = cache_path.read_text(encoding="utf-8")
                self.assertNotIn("secret-token", raw)
                self.assertNotIn("sample@example.invalid", raw)
                self.assertNotIn("device-test-01", raw)
                with cloud_state._LOCK:
                    cloud_state._SOURCE = None
                    cloud_state._ROWS.clear()
                restored = cloud_state.cached_raw_values()
                self.assertEqual(restored["T01"]["value"], 39.4)
                self.assertEqual(restored["T01"]["quality"], "stale")
                with cloud_state._LOCK:
                    cloud_state._SOURCE = None
                    cloud_state._ROWS.clear()

    def test_logging_is_bounded(self):
        for i in range(170):
            cloud_state.log_event("read", "Cloud gelesen", count=i)
        self.assertLessEqual(len(cloud_state.logs()), 150)


if __name__ == "__main__":
    unittest.main()
