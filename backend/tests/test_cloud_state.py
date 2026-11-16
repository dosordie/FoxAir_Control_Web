"""No-network full scan tests with reviewed code kinds and unsupported bisection."""
import unittest
from unittest.mock import patch, Mock

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

    def test_logging_is_bounded(self):
        for i in range(170):
            cloud_state.log_event("read", "Cloud gelesen", count=i)
        self.assertLessEqual(len(cloud_state.logs()), 150)


if __name__ == "__main__":
    unittest.main()
