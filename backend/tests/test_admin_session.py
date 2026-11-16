"""No real cloud writes. Verify reader/admin session security boundaries."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import cloud_config
from backend.main import app


class SessionPermissionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.patches = [
            patch("backend.admin_session.SESSION_FILE", Path(self.tmp.name) / "sessions.json"),
            patch.object(cloud_config, "ADMIN_FILE", Path(self.tmp.name) / "admin.json"),
            patch.object(cloud_config, "CLOUD_FILE", Path(self.tmp.name) / "cloud.json"),
        ]
        for item in self.patches:
            item.start()
        cloud_config.set_admin_password("secure-password-for-tests")
        self.client = TestClient(app, base_url="https://testserver")

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_guest_can_read_but_cannot_write(self):
        self.assertEqual(self.client.get("/api/admin/session").json()["role"], "reader")
        self.assertEqual(self.client.get("/api/registers").status_code, 200)
        with patch("backend.main.write_control") as write:
            response = self.client.post("/api/cloud/write", json={
                "code": "Mode", "value": 1, "expected": 0,
            }, headers={"x-foxair-admin": "1"})
            self.assertEqual(response.status_code, 403)
            write.assert_not_called()

    def test_cookie_auth_requires_header_and_logout_revokes_it(self):
        login = self.client.post("/api/admin/login", json={
            "admin_password": "secure-password-for-tests",
        })
        self.assertEqual(login.status_code, 200, login.text)
        self.assertIn("httponly", login.headers["set-cookie"].lower())
        self.assertIn("samesite=strict", login.headers["set-cookie"].lower())
        self.assertIn("secure", login.headers["set-cookie"].lower())
        self.assertEqual(self.client.get("/api/admin/session").json()["role"], "admin")
        with patch("backend.main.write_control", return_value={"status": "confirmed", "confirmed": True}) as write:
            request = {"code": "Mode", "value": 1, "expected": 0}
            denied = self.client.post("/api/cloud/write", json=request)
            self.assertEqual(denied.status_code, 403)
            accepted = self.client.post("/api/cloud/write", json=request,
                                        headers={"x-foxair-admin": "1"})
            self.assertEqual(accepted.status_code, 200, accepted.text)
            write.assert_called_once_with("Mode", 1, 0)
        logout = self.client.post("/api/admin/logout", json={},
                                  headers={"x-foxair-admin": "1"})
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(self.client.get("/api/admin/session").json()["role"], "reader")

    def test_session_survives_memory_reset_and_stores_no_bearer_token(self):
        from backend import admin_session
        token = admin_session.login()
        self.assertNotIn(token, admin_session.SESSION_FILE.read_text())
        admin_session._SESSIONS.clear()
        self.assertTrue(admin_session.authenticated(token))
        admin_session.logout(token)
        self.assertFalse(admin_session.authenticated(token))

    def test_wrong_password_does_not_create_session(self):
        result = self.client.post("/api/admin/login", json={"admin_password": "wrong"})
        self.assertEqual(result.status_code, 403)
        self.assertEqual(self.client.get("/api/admin/session").json()["role"], "reader")

    def test_session_actions_accept_empty_or_omitted_password_but_keep_guards(self):
        actions = {
            "/api/cloud/account": ("credentials", ("user", "secret", "device")),
            "/api/cloud/devices": ("discover_devices", []),
            "/api/cloud/device-status": ("selected_device_status", {}),
            "/api/cloud/scan": ("cloud_scan_start", {"started": True}),
            "/api/update/request": ("web_request_update", {"requested": True}),
            "/api/warmlink/config": ("warmlink_config", {"host": "192.168.1.50", "port": 2001, "enabled": False}),
        }
        for path, (name, result) in actions.items():
            with self.subTest(path=path), patch("backend.main." + name, return_value=result) as action:
                self.assertEqual(self.client.post(path, json={}, headers={"x-foxair-admin": "1"}).status_code, 403)
                action.assert_not_called()
        self.client.post("/api/admin/login", json={"admin_password": "secure-password-for-tests"})
        for path, (name, result) in actions.items():
            with self.subTest(path=path), patch("backend.main." + name, return_value=result) as action:
                for body in ({}, {"admin_password": ""}):
                    self.assertEqual(self.client.post(path, json=body, headers={"x-foxair-admin": "1"}).status_code, 200)
                action.reset_mock()
                self.assertEqual(self.client.post(path, json={}).status_code, 403)
                self.assertEqual(self.client.post(path, json={}, headers={"x-foxair-admin": "1", "origin": "https://other.invalid"}).status_code, 403)
                action.assert_not_called()

    def test_login_still_requires_nonempty_password(self):
        for body in ({}, {"admin_password": ""}):
            self.assertEqual(self.client.post("/api/admin/login", json=body).status_code, 422)

    def test_lte_mutations_require_session_header_and_same_origin(self):
        for path, payload, name in (
            ("/api/warmlink/config/save", {"host": "192.168.1.50", "port": 2001, "enabled": True}, "save_warmlink"),
            ("/api/warmlink/write", {"code": "R02", "value": 35.5, "expected": 35}, "write_warmlink_control"),
        ):
            self.client.post("/api/admin/logout", json={}, headers={"x-foxair-admin": "1"})
            with self.subTest(path=path), patch("backend.main." + name, return_value={"ok": True}) as action:
                self.assertEqual(self.client.post(path, json=payload, headers={"x-foxair-admin": "1"}).status_code, 403)
                self.client.post("/api/admin/login", json={"admin_password": "secure-password-for-tests"})
                self.assertEqual(self.client.post(path, json=payload).status_code, 403)
                self.assertEqual(self.client.post(path, json=payload, headers={"x-foxair-admin": "1", "origin": "https://other.invalid"}).status_code, 403)
                action.assert_not_called()
                self.assertEqual(self.client.post(path, json=payload, headers={"x-foxair-admin": "1"}).status_code, 200)
                action.assert_called_once()

    def test_arbitrary_code_rejected_before_control(self):
        self.client.post("/api/admin/login", json={"admin_password": "secure-password-for-tests"})
        with patch("backend.main.write_control") as write:
            result = self.client.post("/api/cloud/write", json={
                "code": "SG01", "value": 7, "expected": 0,
            }, headers={"x-foxair-admin": "1"})
            self.assertEqual(result.status_code, 422)
            write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
