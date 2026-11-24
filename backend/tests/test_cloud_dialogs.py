"""Only safe, catalog-backed codes are offered by read-only dialogs."""
import unittest
from unittest.mock import patch

from backend import cloud_dialogs
from backend.cloud_read import UnsupportedCloudCode


class CloudDialogTests(unittest.TestCase):
    def setUp(self):
        cloud_dialogs._last_read.clear()

    def test_defs_include_editable_controls_and_read_only_faults(self):
        catalog = [
            {"code": "SG01"}, {"code": "SG Status"}, {"code": "H36"},
            {"code": "CP1-1"}, {"code": "TimerMuteOnHour"},
            {"code": "M1 Start"}, {"code": "Fault1"}, {"code": "O01~023"}, {"code": "S01~S10"},
        ]
        with patch("backend.cloud_dialogs.catalog", return_value=catalog):
            dialogs = cloud_dialogs.definitions()
        self.assertEqual({row["id"] for row in dialogs},
                         {"wp", "at", "sg", "silent", "timer", "fault", "decoder"})
        self.assertEqual({row["id"] for row in dialogs if row["read_only"]}, {"fault", "decoder"})
        decoder = next(row for row in dialogs if row["id"] == "decoder")
        self.assertEqual(decoder["local_registers"], [2018, 2019, 2034])
        self.assertEqual(decoder["codes"], ["O01~023", "S01~S10"])
        sg = next(row for row in dialogs if row["id"] == "sg")
        self.assertEqual(sg["codes"], ["SG01", "SG Status"])
        at = next(row for row in dialogs if row["id"] == "at")
        self.assertEqual([point["register"] for point in at["curve_points"]],[1250,1251,1252,1235,1253,1254,1255])
        self.assertNotIn(1250,at["registers"])  # Missing mapping grants are not guessed.

    def test_cannot_trigger_unknown_dynamic_code(self):
        with patch("backend.cloud_dialogs.catalog", return_value=[]):
            with self.assertRaises(ValueError):
                cloud_dialogs.refresh("arbitrary; rm -rf /")

    def test_refresh_is_throttled_and_preserves_supported_results(self):
        rows = [{"code": "SG01"}, {"code": "SG02"}]
        class Reader:
            def read_codes(self, codes):
                if "SG02" in codes:
                    raise UnsupportedCloudCode("unsupported")
                return {"SG01": {"value": "2"}}
        with patch("backend.cloud_dialogs.catalog", return_value=rows), \
                patch("backend.cloud_dialogs.cached_raw_values", return_value={}), \
                patch("backend.cloud_dialogs._reader", return_value=Reader()), \
                patch("backend.cloud_dialogs.merge") as merge, \
                patch("backend.cloud_dialogs.log_event"):
            first = cloud_dialogs.refresh("sg")
            second = cloud_dialogs.refresh("sg")
        self.assertTrue(first["updated"])
        self.assertEqual(first["count"], 1)
        self.assertEqual(first["unsupported"], 1)
        self.assertFalse(second["updated"])
        self.assertEqual(second["reason"], "rate_limit")
        merge.assert_called_once()


if __name__ == "__main__":
    unittest.main()
