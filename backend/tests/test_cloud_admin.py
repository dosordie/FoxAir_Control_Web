"""HTTP admin-gate, cloud config and source-backed group tests. No live cloud."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.main import app
from backend import cloud_config


class CloudAdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.admin_path = Path(self.tmp.name) / "admin.json"
        self.cloud_path = Path(self.tmp.name) / "cloud.json"
        self.patch_admin = patch.object(cloud_config, "ADMIN_FILE", self.admin_path)
        self.patch_cloud = patch.object(cloud_config, "CLOUD_FILE", self.cloud_path)
        self.patch_admin.start()
        self.patch_cloud.start()
        cloud_config.set_admin_password("A-strong-admin-password!")
        self.https = TestClient(app, base_url="https://testserver")
        self.http = TestClient(app, base_url="http://testserver")

    def tearDown(self):
        self.patch_admin.stop()
        self.patch_cloud.stop()
        self.tmp.cleanup()

    def test_get_status_never_leaks_secrets(self):
        with patch.dict("os.environ", {"FOXAIR_CLOUD_USER": "", "FOXAIR_CLOUD_PASSWORD": "",
                                       "FOXAIR_CLOUD_DEVICE_CODE": ""}):
            self.assertTrue(self.https.get("/api/cloud/config").json()["admin_enabled"])
            cloud_config.save_cloud("sample-user", "sample-secret", "test-code-123")
            result = self.https.get("/api/cloud/config")
            data = result.json()
            self.assertTrue(data["configured"])
            self.assertNotIn("sample-user", result.text)
            self.assertNotIn("sample-secret", result.text)
            self.assertNotIn("test-code-123", result.text)

    def test_http_rejected(self):
        result = self.http.post("/api/cloud/config", json={
            "admin_password": "A-strong-admin-password!",
            "username": "test-user",
            "password": "test-password",
            "device_code": "device-123",
        })
        self.assertEqual(result.status_code, 403)

    def test_wrong_password_rejected(self):
        result = self.https.post("/api/cloud/config", json={
            "admin_password": "incorrect",
            "username": "test-user",
            "password": "test-password",
            "device_code": "device-123",
        })
        self.assertEqual(result.status_code, 403)

    def test_https_save_and_keep_existing_password(self):
        with patch.dict("os.environ", {"FOXAIR_CLOUD_USER": "", "FOXAIR_CLOUD_PASSWORD": "",
                                       "FOXAIR_CLOUD_DEVICE_CODE": ""}):
            ok = self.https.post("/api/cloud/config", json={
                "admin_password": "A-strong-admin-password!",
                "username": "test-user",
                "password": "test-password",
                "device_code": "device-123",
            })
            self.assertEqual(ok.status_code, 200, ok.text)
            ok2 = self.https.post("/api/cloud/config", json={
                "admin_password": "A-strong-admin-password!",
                "device_code": "device-456",
            })
            self.assertEqual(ok2.status_code, 200, ok2.text)
            self.assertEqual(cloud_config.credentials(),
                             ("test-user", "test-password", "device-456"))

    def test_device_discovery_requires_password(self):
        with patch("backend.main.discover_devices", return_value=[
            {"deviceCode": "example", "deviceNickName": "WP"}
        ]) as discover:
            bad = self.https.post("/api/cloud/devices", json={"admin_password": "wrong"})
            self.assertEqual(bad.status_code, 403)
            discover.assert_not_called()
            good = self.https.post("/api/cloud/devices",
                                   json={"admin_password": "A-strong-admin-password!"})
            self.assertEqual(good.status_code, 200)
            self.assertEqual(good.json()["items"][0]["deviceNickName"], "WP")


class RegisterGroupTests(unittest.TestCase):
    def test_groups_and_filter(self):
        client = TestClient(app)
        groups = client.get("/api/register-groups").json()["items"]
        for code in ("H", "P", "T", "D", "R"):
            self.assertTrue(any(g["group"] == code for g in groups))
        result = client.get("/api/registers?group=H&limit=200")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(all(r["group"] == "H" for r in result.json()["items"]))


if __name__ == "__main__":
    unittest.main()
