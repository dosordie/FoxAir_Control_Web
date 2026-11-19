from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app
from backend import cloud_config, admin_session, users


class UsersTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            patch.object(cloud_config, "STATE_DIR", self.root),
            patch.object(cloud_config, "ADMIN_FILE", self.root / "admin.json"),
            patch.object(admin_session, "SESSION_FILE", self.root / "sessions.json"),
        ]
        for p in self.patches:
            p.start()
        cloud_config.set_admin_password("test-fallback-password")
        self.client = TestClient(
            app, base_url="https://testserver", headers={"X-FoxAir-Admin": "1"}
        )
        self.client.post(
            "/api/admin/login", json={"admin_password": "test-fallback-password"}
        )

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def add(self, name, role, allowed=[]):
        result = self.client.post(
            "/api/accounts/user",
            json={
                "username": name,
                "role": role,
                "password": "test-user-password",
                "allowed_registers": allowed,
            },
        )
        self.assertEqual(result.status_code, 200, result.text)

    def login(self, name):
        c = TestClient(
            app, base_url="https://testserver", headers={"X-FoxAir-Admin": "1"}
        )
        result = c.post(
            "/api/admin/login",
            json={"username": name, "admin_password": "test-user-password"},
        )
        self.assertEqual(result.status_code, 200, result.text)
        return c

    def test_role_and_register_boundaries(self):
        self.add("viewer", "reader")
        self.add("operator", "operator", [1158])
        viewer = self.login("viewer")
        operator = self.login("operator")
        self.assertEqual(viewer.get("/api/admin/session").json()["role"], "reader")
        self.assertEqual(viewer.get("/api/accounts").status_code, 403)
        self.assertEqual(operator.get("/api/accounts").status_code, 403)
        body = {"transport": "cloud", "value": "35", "expected": "34"}
        with patch(
            "backend.parameter_write.write",
            return_value={"confirmed": True, "value": 35},
        ) as write:
            self.assertEqual(
                viewer.post("/api/parameters/1158/write", json=body).status_code, 403
            )
            self.assertEqual(
                operator.post("/api/parameters/1012/write", json=body).status_code, 403
            )
            write.assert_not_called()
            self.assertEqual(
                operator.post("/api/parameters/1158/write", json=body).status_code, 200
            )
        audit = self.client.get("/api/accounts/audit").json()["items"]
        self.assertEqual(audit[0]["user"], "operator")
        self.assertEqual(audit[0]["request"]["expected"], "34")
        self.assertTrue(audit[0]["result"]["confirmed"])

    def test_blocked_user_and_role_change_invalidate_sessions(self):
        self.add("other", "admin")
        c = self.login("other")
        self.assertEqual(c.get("/api/accounts").status_code, 200)
        self.client.post(
            "/api/accounts/user",
            json={"username": "other", "role": "reader", "enabled": False},
        )
        self.assertFalse(c.get("/api/admin/session").json()["authenticated"])
        self.assertEqual(c.get("/api/accounts").status_code, 403)

    def test_guest_policy_and_fallback_login(self):
        self.client.post(
            "/api/accounts/policy", json={"guest_read": False, "sso_mapping": {}}
        )
        guest = TestClient(app, base_url="https://testserver")
        self.assertEqual(guest.get("/api/register-groups").status_code, 401)
        self.assertEqual(
            guest.post("/api/parameters/refresh", json={}).status_code, 401
        )
        self.assertEqual(guest.get("/api/health").status_code, 200)
        self.assertEqual(
            guest.post(
                "/api/admin/login", json={"admin_password": "test-fallback-password"}
            ).status_code,
            200,
        )

    def test_sessions_revoke_and_csrf(self):
        self.add("other", "admin")
        c = self.login("other")
        sessions = self.client.get("/api/accounts/sessions").json()["items"]
        target = next(s["id"] for s in sessions if s["username"] == "other")
        self.assertEqual(
            self.client.post(
                "/api/accounts/sessions/revoke",
                json={"id": target},
                headers={"Origin": "https://evil.invalid"},
            ).status_code,
            403,
        )
        self.assertEqual(c.get("/api/accounts").status_code, 200)
        self.client.post("/api/accounts/sessions/revoke", json={"id": target})
        self.assertEqual(c.get("/api/accounts").status_code, 403)

    def test_encrypted_backup_and_restore(self):
        self.add("viewer", "reader")
        cloud_config._atomic_json(
            self.root / "cloud.json", {"password": "private-cloud-value"}
        )
        result = self.client.post(
            "/api/accounts/backup", json={"password": "backup-password-secure"}
        )
        archive = result.json()["archive"]
        self.assertNotIn("private-cloud-value", archive)
        self.assertEqual(
            self.client.post(
                "/api/accounts/restore",
                json={"password": "incorrect-password", "archive": archive},
            ).status_code,
            422,
        )
        self.assertEqual(self.client.get("/api/accounts").status_code, 200)
        self.client.post(
            "/api/accounts/user",
            json={"username": "viewer", "role": "reader", "enabled": False},
        )
        self.assertEqual(
            self.client.post(
                "/api/accounts/restore",
                json={"password": "backup-password-secure", "archive": archive},
            ).status_code,
            200,
        )
        self.assertTrue(users.account("viewer"))
        self.assertEqual(self.client.get("/api/accounts").status_code, 403)
        self.assertTrue(cloud_config.verify_admin("test-fallback-password"))

    def test_no_password_hashes_disclosed_or_reserved_admin_changed(self):
        self.add("viewer", "reader")
        listing = self.client.get("/api/accounts").text
        self.assertNotIn("test-user-password", listing)
        self.assertNotIn("salt", listing)
        self.assertNotIn("hash", listing)
        self.assertEqual(
            self.client.post(
                "/api/accounts/user", json={"username": "admin", "role": "reader"}
            ).status_code,
            422,
        )

    def test_sso_uses_local_reader_role_and_revocation_stops_auto_login(self):
        import os, secrets, json
        from backend.server import TCPPeerApp

        self.add("viewer", "reader")
        users.save({**users.read(), "sso_mapping": {"test-subject": "viewer"}})
        secret = secrets.token_urlsafe(48)
        path = self.root / "sso.json"
        path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "provider": "authelia",
                    "trusted_proxy_ips": ["192.0.2.10"],
                }
            )
        )
        with patch.dict(
            os.environ,
            {
                "FOXAIR_SSO_CONFIG": str(path),
                "FOXWEB_SSO_SECRET": secret,
                "FOXAIR_TRUSTED_PROXY_IPS": "192.0.2.10",
            },
        ):
            c = TestClient(
                TCPPeerApp(app),
                base_url="https://testserver",
                client=("192.0.2.10", 50000),
                headers={
                    "Remote-User": "test-subject",
                    "X-FoxAir-SSO-Secret": secret,
                    "X-FoxAir-SSO-Authenticated": "1",
                },
            )
            result = c.get("/api/admin/session")
            self.assertEqual(result.json()["role"], "reader")
            self.assertTrue(result.json()["authenticated"])
            self.assertEqual(c.get("/api/accounts").status_code, 403)
            entry = next(
                s
                for s in self.client.get("/api/accounts/sessions").json()["items"]
                if s["username"] == "viewer"
            )
            self.client.post("/api/accounts/sessions/revoke", json={"id": entry["id"]})
            self.assertFalse(c.get("/api/admin/session").json()["authenticated"])
