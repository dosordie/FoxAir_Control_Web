import unittest
from fastapi.testclient import TestClient
from backend.main import app


class ApiTests(unittest.TestCase):
    def test_favorites_filter_applies_before_the_catalog_limit_without_bus_access(self):
        from unittest.mock import patch
        with patch('backend.main.open_warmlink') as active:
            response=self.client.get('/api/registers?favorites_only=true&favorite=1158&favorite=2077&favorite=99999&limit=1')
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.json()['items']),1)
        self.assertIn(response.json()['items'][0]['register'],(1158,2077))
        active.assert_not_called()

    def test_empty_favorites_are_empty_and_invalid_or_excessive_ids_are_rejected(self):
        self.assertEqual(self.client.get('/api/registers?favorites_only=true').json()['items'],[])
        self.assertEqual(self.client.get('/api/registers?favorites_only=true&favorite=invalid').status_code,422)
        self.assertEqual(self.client.get('/api/registers?favorites_only=true'+('&favorite=1158'*1001)).status_code,422)
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_available_transports(self):
        response = self.client.get("/api/transports")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 4)
        self.assertTrue(response.json()["live_supported"])

    def test_cloud_unconfigured_has_no_values(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"FOXAIR_CLOUD_USER": "", "FOXAIR_CLOUD_PASSWORD": "",
                                       "FOXAIR_CLOUD_DEVICE_CODE": ""}), patch("backend.last_values.store.values", return_value={}):
            data = self.client.get("/api/dashboard?transport=cloud").json()
        self.assertEqual(data["status"], "unavailable")
        self.assertTrue(all(value is None for value in data["metrics"].values()))

    def test_cloud_outage_retains_last_value_but_never_reports_online(self):
        from unittest.mock import patch
        from backend.cloud_read import CloudError
        timestamp = "2026-11-15T08:15:00+00:00"
        stale = {"return": {"value": 37.5, "unit": "°C", "raw": None,
                            "quality": "stale", "timestamp": timestamp}}
        with patch("backend.main.cloud_dashboard", side_effect=CloudError("Cloud timeout")), \
                patch("backend.main.cached_dashboard", return_value=stale):
            result = self.client.get("/api/dashboard?transport=cloud")
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertEqual(data["status"], "unavailable")
        self.assertEqual(data["metrics"]["return"]["value"], 37.5)
        self.assertEqual(data["metrics"]["return"]["quality"], "stale")
        self.assertEqual(data["metrics"]["return"]["timestamp"], timestamp)

    def test_search(self):
        response = self.client.get("/api/registers?query=D14")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(row["code"] == "D14" for row in response.json()["items"]))

    def test_parameter_write_requires_admin_before_transport_access(self):
        from unittest.mock import patch
        with patch("backend.parameter_write.write") as writer:
            result = self.client.post("/api/parameters/1105/write", json={"transport":"warmlink_raw","value":"2.5","expected":"10"})
        self.assertIn(result.status_code, (401,403))
        writer.assert_not_called()

    def test_no_write_endpoint(self):
        response = self.client.post("/api/registers/1158/write", json={"value": 35})
        self.assertIn(response.status_code, (404, 405))

    def test_standard_disabled_by_default(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"FOXAIR_ENABLE_STANDARD_MODBUS": "0",
                                       "FOXAIR_STANDARD_HOST": "127.0.0.1"}):
            item = next(t for t in self.client.get("/api/transports").json()["items"]
                        if t["id"] == "standard_modbus")
            self.assertFalse(item["read_supported"])

    def test_unknown_transport_rejected(self):
        self.assertEqual(self.client.get("/api/dashboard?transport=unsafe").status_code, 400)


if __name__ == "__main__":
    unittest.main()
