"""Only allowlisted Mode/R02 PHNIX controls, no retries and verified readback."""
import unittest
from unittest.mock import Mock, patch

from backend import cloud_write
from backend.cloud_write import WriteConflictError, WriteValidationError
from backend.cloud_read import CloudError


class CloudFirstWriteTests(unittest.TestCase):
    def setUp(self):
        self.reader = Mock()
        self.reader.token = "fake"
        self.reader.device_code = "device-in-tests"
        self.reader._ok.side_effect = lambda x: bool(x.get("isReusltSuc"))
        self.reader._post.return_value = {"isReusltSuc": True}
        self.acc = ("test@example.invalid", "not-a-secret", "device-in-tests")
        self.patches = [
            patch("backend.cloud_write.credentials", return_value=self.acc),
            patch("backend.cloud_write._reader", return_value=self.reader),
            patch("backend.cloud_write.merge"),
            patch("backend.cloud_write.log_event"),
            patch("backend.cloud_write.time.sleep"),
            patch.object(cloud_write, "_LAST_WRITE", 0.0),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def test_mode_writes_once_with_readback(self):
        self.reader.read_codes.side_effect = [
            {"Mode": {"value": "0"}},
            {"Mode": {"value": "1"}},
        ]
        reply = cloud_write.write_control("Mode", 1, 0)
        self.assertTrue(reply["confirmed"])
        self.assertEqual(reply["status"], "confirmed")
        self.reader._post.assert_called_once_with(
            "app/device/control?lang=en",
            {"appId": "16", "param": [{"deviceCode": "device-in-tests",
                                     "protocolCode": "Mode", "value": "1"}]},
            token="fake",
        )
        self.assertEqual(self.reader.read_codes.call_count, 2)

    def test_power_uses_binary_engineering_payload_and_readback(self):
        self.reader.read_codes.side_effect = [{"Power":{"value":0}},{"Power":{"value":1}}]
        self.assertTrue(cloud_write.write_control("Power",1,0)["confirmed"])
        self.reader._post.assert_called_once()
        self.assertEqual(self.reader._post.call_args.args[1]["param"][0]["value"],"1")

    def test_silent_rejects_nonbinary_before_network(self):
        with self.assertRaises(WriteValidationError): cloud_write.write_control("H22",2,0)
        self.reader.read_codes.assert_not_called()

    def test_r02_uses_live_r10_r11_limits_and_cloud_engineering_value(self):
        self.reader.read_codes.side_effect = [
            {"R02": {"value": "35.0"}, "R10": {"value": 25}, "R11": {"value": 53}},
            {"R02": {"value": "42.5"}},
        ]
        result = cloud_write.write_control("R02", "42,5", "35.0")
        self.assertTrue(result["confirmed"])
        payload = self.reader._post.call_args.args[1]
        self.assertEqual(payload["param"][0]["value"], "42.5")

    def test_stale_expected_value_refuses_any_write(self):
        self.reader.read_codes.return_value = {"Mode": {"value": "1"}}
        with self.assertRaises(WriteConflictError):
            cloud_write.write_control("Mode", 2, 0)
        self.reader._post.assert_not_called()

    def test_soll_outside_live_bounds_refuses_any_write(self):
        self.reader.read_codes.return_value = {
            "R02": {"value": 35}, "R10": {"value": 30}, "R11": {"value": 45}
        }
        with self.assertRaises(WriteValidationError):
            cloud_write.write_control("R02", 46, 35)
        self.reader._post.assert_not_called()

    def test_mode_unapproved_value_refuses_before_network(self):
        with self.assertRaises(WriteValidationError):
            cloud_write.write_control("Mode", 7, 0)
        self.reader.read_codes.assert_not_called()

    def test_network_error_does_not_repeat_control(self):
        self.reader.read_codes.return_value = {"Mode": {"value": "0"}}
        self.reader._post.side_effect = CloudError("Cloud-Timeout")
        result = cloud_write.write_control("Mode", 1, 0)
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["status"], "unconfirmed")
        self.reader._post.assert_called_once()
        self.assertEqual(self.reader.read_codes.call_count, 1)

    def test_readback_mismatch_not_claimed_as_success(self):
        self.reader.read_codes.side_effect = [
            {"Mode": {"value": 0}},
            {"Mode": {"value": 0}},
        ]
        result = cloud_write.write_control("Mode", 1, 0)
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["status"], "unconfirmed")
        self.reader._post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
