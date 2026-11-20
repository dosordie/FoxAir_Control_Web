import unittest
from unittest.mock import patch
from backend.cloud_mapping_overrides import supplement_catalog
from backend.cloud_read import CloudReader, project_dashboard
from backend.parameter_write import cloud_format


class PumpCloudMappingTests(unittest.TestCase):
    def test_numeric_aliases_are_live_read_only_and_leave_empty_pwm_codes_unmapped(
        self,
    ):
        rows = supplement_catalog([{"code": "T_PWM_Out2", "register": None}])
        for code in ("2115", "2116"):
            row = next(r for r in rows if r["code"] == code)
            self.assertEqual(row["register"], int(code))
            self.assertEqual((row["kind"], row["confidence"]), ("live", "confirmed"))
            self.assertFalse(row["write_allowed"])
            with patch("backend.cloud_state.catalog", return_value=rows):
                with self.assertRaises(ValueError):
                    cloud_format(code, 50)
        self.assertIsNone(rows[0]["register"])
        self.assertEqual(supplement_catalog(rows), rows)
        with self.assertRaises(ValueError):
            supplement_catalog([{"code": "2115", "register": 2054}])

    def test_cloud_zero_survives_and_empty_feedback_is_not_a_value(self):
        reader = CloudReader("test", "test", "test")
        reply = {
            "error_code": "0",
            "isReusltSuc": True,
            "objectResult": [
                {"code": "2115", "value": "0", "dataType": "DIGI1"},
                {"code": "2116", "value": ""},
            ],
        }
        with patch.object(reader, "_request_auth", return_value=reply):
            values = reader.read_codes(["2115", "2116"])
        self.assertEqual(values["2115"]["value"], "0")
        self.assertNotIn("2116", values)
        metric = project_dashboard(values)["pump_pwm"]
        self.assertEqual(metric["value"], "0")
        self.assertEqual(metric["unit"], "%")
