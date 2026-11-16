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

    def test_cloud_insights_require_admin_and_same_origin_before_querying(self):
        requests = [('/api/cloud/history', {'address':'2046','start':'2026-11-15 00:00:00','end':'2026-11-16 00:00:00'}),
                    ('/api/cloud/insights/ota', {}), ('/api/cloud/insights/metadata', {}),
                    ('/api/cloud/insights/ai', {}), ('/api/cloud/service-enum', {'key':'opaque-reference'})]
        with patch('backend.cloud_insights.request', return_value={'cached':False}) as query:
            for path, body in requests:
                with self.subTest(path=path):
                    self.assertEqual(self.https.post(path,json=body).status_code,403)
                    self.assertEqual(self.http.post(path,json=body).status_code,403)
                    self.assertEqual(self.https.post(path,json={**body,'admin_password':'A-strong-admin-password!'},headers={'origin':'https://other-site'}).status_code,403)
            query.assert_not_called()
            for path, body in requests:
                self.assertEqual(self.https.post(path,json={**body,'admin_password':'A-strong-admin-password!'}).status_code,200)
            self.assertEqual(query.call_count,len(requests))

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

    def test_web_update_requires_https_and_admin_password(self):
        with patch("backend.main.web_request_update", return_value={"requested": True}) as update:
            insecure = self.http.post("/api/update/request", json={
                "admin_password": "A-strong-admin-password!"
            })
            self.assertEqual(insecure.status_code, 403)
            unauthorized = self.https.post("/api/update/request", json={
                "admin_password": "incorrect"
            })
            self.assertEqual(unauthorized.status_code, 403)
            update.assert_not_called()
            authorized = self.https.post("/api/update/request", json={
                "admin_password": "A-strong-admin-password!"
            })
            self.assertEqual(authorized.status_code, 200)
            update.assert_called_once_with()

    def test_account_disclosure_requires_admin_password(self):
        with patch.dict("os.environ", {"FOXAIR_CLOUD_USER": "", "FOXAIR_CLOUD_PASSWORD": "",
                                       "FOXAIR_CLOUD_DEVICE_CODE": ""}):
            cloud_config.save_cloud("admin@example.invalid", "hidden-secret", "dev-987")
            denied = self.https.post("/api/cloud/account", json={"admin_password": "incorrect"})
            self.assertEqual(denied.status_code, 403)
            authorized = self.https.post("/api/cloud/account", json={
                "admin_password": "A-strong-admin-password!"
            })
            self.assertEqual(authorized.status_code, 200)
            self.assertEqual(authorized.json(),
                             {"username": "admin@example.invalid", "device_code": "dev-987"})
            self.assertNotIn("hidden-secret", authorized.text)

    def test_proxy_https_header_must_come_from_configured_peer(self):
        data = {"admin_password": "A-strong-admin-password!"}
        headers = {"x-forwarded-proto": "https", "origin": "https://testserver"}
        with patch.dict("os.environ", {"FOXAIR_TRUSTED_PROXY_IPS": ""}):
            untrusted = self.http.post("/api/cloud/account", json=data, headers=headers)
            self.assertEqual(untrusted.status_code, 403)
        with patch.dict("os.environ", {"FOXAIR_TRUSTED_PROXY_IPS": "testclient"}):
            trusted = self.http.post("/api/cloud/account", json=data, headers=headers)
            self.assertEqual(trusted.status_code, 200)

    def test_log_endpoint_contains_no_account_credentials(self):
        from backend.cloud_state import log_event
        log_event("scan", "Cloud-Katalogscan gestartet", count=535)
        response = self.https.get("/api/cloud/logs")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(row["kind"] == "scan" for row in response.json()["items"]))
        self.assertNotIn("admin@example.invalid", response.text)

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
