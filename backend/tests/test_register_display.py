"""Ensure numeric MAIN sort and source-backed human-readable cloud enums."""
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from backend.catalog import load_registers, public_register, search_registers
from backend import cloud_state


class HumanReadableRegisterTests(unittest.TestCase):
    def test_parameters_sorted_by_code_before_limit(self):
        source = {"1012": {"code": "R10"}, "1158": {"code": "R02"},
                  "2045": {"code": "R01"}, "1001": {"code": ""}}
        with patch("backend.catalog.load_registers", return_value=source):
            rows = search_registers("", limit=2)
        self.assertEqual([r["code"] for r in rows], ["R01", "R02"])

    def test_reviewed_enum_labels(self):
        defs = load_registers()
        self.assertEqual(public_register("1012", defs["1012"])["value_map"]["1"], "Heizen")
        self.assertEqual(cloud_state.display_label(1012, "1.0"), "Heizen")
        self.assertEqual(cloud_state.display_label(1011, 1), "Ein")
        self.assertEqual(cloud_state.display_label(1236, "2"), "7-Punkt-Kennlinie")
        self.assertEqual(cloud_state.display_label(2045, "39.2"), None)
        self.assertEqual(cloud_state.display_label(None, 1), None)

    def test_cloud_rows_sorted_by_register_not_textual_code(self):
        rows = [
            {"code": "H36", "register": 1236, "kind": "static"},
            {"code": "Mode", "register": 1012, "kind": "static"},
            {"code": "T01", "register": 2045, "kind": "live"},
            {"code": "UNMAPPED", "register": None, "kind": "other"},
        ]
        now = datetime.now(timezone.utc).isoformat()
        state = {row["code"]: {"value": 1, "timestamp": now, "unit": ""}
                 for row in rows}
        with patch("backend.cloud_state._reset_if_changed"), \
                patch("backend.cloud_state.catalog", return_value=rows), \
                patch.object(cloud_state, "_ROWS", state), \
                patch.object(cloud_state, "_STATUS", "complete"):
            result = cloud_state.value_rows()
        codes = [row["code"] for row in result["items"]]
        self.assertEqual(codes, ["Mode", "H36", "T01", "UNMAPPED"])
        self.assertEqual(result["items"][0]["display_value"], "Heizen")


if __name__ == "__main__":
    unittest.main()
