"""Cloud contract tests; no real PHNIX credentials or network traffic."""
import unittest
from unittest.mock import patch

from backend.cloud_read import CLOUD_REGISTERS, CloudReader, CloudError, cloud_configured


class CloudReadTests(unittest.TestCase):
    def test_config_required(self):
        with patch.dict("os.environ", {"FOXAIR_CLOUD_USER": "", "FOXAIR_CLOUD_PASSWORD": "",
                                       "FOXAIR_CLOUD_DEVICE_CODE": ""}):
            self.assertFalse(cloud_configured())

    def test_login_reuses_token_and_sends_only_read(self):
        client = CloudReader("fake-account", "fake-password", "fake-device")
        calls = []

        def post(endpoint, payload, *, token=None):
            calls.append((endpoint, payload, token))
            if endpoint == "app/user/login":
                return {"isReusltSuc": True, "objectResult": {"x-token": "mock-token"}}
            self.assertEqual(token, "mock-token")
            self.assertEqual(payload["deviceCode"], "fake-device")
            return {"isReusltSuc": True, "objectResult": [
                {"code": "T04", "value": "-1.5"}, {"code": "T08", "value": 42.0},
            ]}

        with patch.object(client, "_post", side_effect=post):
            rows = client.read_codes(["T04", "T08"])
            self.assertEqual(rows["T04"]["value"], "-1.5")
            self.assertEqual(rows["T08"]["value"], 42.0)
            client.read_codes(["T04"])
        self.assertEqual([item[0] for item in calls].count("app/user/login"), 1)
        self.assertTrue(all(x[0] in ("app/user/login", "app/device/getDataByCode") for x in calls))

    def test_nonwhitelisted_cloud_codes_rejected(self):
        client = CloudReader("fake", "fake", "fake")
        with self.assertRaises(CloudError):
            client.read_codes(["T200"])
        self.assertIsNone(client.token)

    def test_empty_cloud_values_are_unavailable_but_zero_valid(self):
        client = CloudReader("fake", "fake", "fake")
        client.token = "fake-token"
        response = {"isReusltSuc": True, "objectResult": [
            {"code": "T04", "value": ""},
            {"code": "T08", "value": 0},
        ]}
        with patch.object(client, "_post", return_value=response):
            result = client.read_codes(["T04", "T08"])
        self.assertNotIn("T04", result)
        self.assertEqual(result["T08"]["value"], 0)

    def test_live_heartbeat_is_dedicated_and_throttled(self):
        client = CloudReader("fake", "fake", "device-test")
        calls = []
        with patch.object(client, "_request_auth",
                          side_effect=lambda endpoint, payload: (
                              calls.append((endpoint, payload)) or
                              {"isReusltSuc": True}
                          )), patch("backend.cloud_read.time.sleep") as pause:
            self.assertTrue(client.app_heartbeat())
            self.assertFalse(client.app_heartbeat())
        self.assertEqual(len(calls), 1)
        endpoint, payload = calls[0]
        self.assertEqual(endpoint, "app/device/control")
        self.assertEqual(payload, {"param": [{
            "deviceCode": "device-test", "protocolCode": "app_heartbeat",
            "value": "23205",
        }]})
        pause.assert_called_once_with(1.0)

    def test_initial_dashboard_does_not_send_heartbeat(self):
        from backend.cloud_read import read_dashboard
        client = CloudReader("fake", "fake", "device-test")
        with patch("backend.cloud_read._reader", return_value=client), \
                patch.object(client, "read_codes", return_value={"T04": {"value": 3.4}}), \
                patch.object(client, "app_heartbeat") as heartbeat:
            data = read_dashboard(live=False)
            self.assertEqual(data["outdoor"]["value"], 3.4)
            heartbeat.assert_not_called()

    def test_live_dashboard_sends_heartbeat_before_read(self):
        from backend.cloud_read import read_dashboard
        client = CloudReader("fake", "fake", "device-test")
        order = []
        with patch("backend.cloud_read._reader", return_value=client), \
                patch.object(client, "read_codes",
                             side_effect=lambda codes: (order.append("read") or {})), \
                patch.object(client, "app_heartbeat",
                             side_effect=lambda: (order.append("heartbeat") or True)):
            read_dashboard(live=True)
        self.assertEqual(order, ["heartbeat", "read"])

    def test_discovery_merges_house_devices_if_main_list_empty(self):
        reader = CloudReader("example", "not-a-real-password", "device-1")
        def fake_request(endpoint, payload, *, method="POST"):
            if endpoint == "app/device/deviceList":
                return {"isReusltSuc": True, "objectResult": []}
            if endpoint == "house/info/listOwnerHouses":
                self.assertEqual(method, "GET")
                return {"isReusltSuc": True, "objectResult": [{
                    "id": "123", "houseName": "Testhaus",
                }]}
            if endpoint == "houseRelDevice/v4/selectHouseToDeviceData":
                self.assertEqual(payload["houseId"], "123")
                return {"isReusltSuc": True, "objectResult": {"data": [{
                    "houseRelDeviceList": [{"deviceCode": "device-1",
                                            "deviceNickName": "Wärmepumpe"}],
                    "roomInfoResultList": [{"houseRelDeviceList": []}],
                }]}}
            raise AssertionError("unexpected endpoint " + endpoint)

        with patch.object(reader, "_request_auth", side_effect=fake_request):
            items = reader.devices()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["deviceCode"], "device-1")
        self.assertEqual(items[0]["houseName"], "Testhaus")

    def test_all_source_cloud_codes_are_validated(self):
        from backend.cloud_state import catalog
        rows = [{"code": "T04"}, {"code": "H36"}]
        with patch("backend.cloud_state.catalog", return_value=rows):
            reader = CloudReader("fake", "fake", "fake")
            reader.token = "fake-token"
            with patch.object(reader, "_request_auth", return_value={
                "isReusltSuc": True,
                "objectResult": [{"code": "H36", "value": "2"}],
            }):
                self.assertEqual(reader.read_codes(["H36"])["H36"]["value"], "2")
                with self.assertRaises(CloudError):
                    reader.read_codes(["T200"])

    def test_known_mapping_includes_verified_dashboard_codes(self):
        self.assertEqual(CLOUD_REGISTERS[2048], "T04")
        self.assertEqual(CLOUD_REGISTERS[2047], "T08")
        self.assertEqual(CLOUD_REGISTERS[2035], "T40")
        self.assertEqual(CLOUD_REGISTERS[2036], "T41")


if __name__ == "__main__":
    unittest.main()
