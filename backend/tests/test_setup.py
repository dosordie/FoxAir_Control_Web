from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import cloud_config, setup
from backend.main import app


class SetupTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for item in (
            patch.object(cloud_config, "STATE_DIR", root),
            patch.object(cloud_config, "ADMIN_FILE", root / "admin.json"),
        ):
            item.start()
            self.addCleanup(item.stop)
        self.client = TestClient(
            app, base_url="https://testserver", headers={"X-FoxAir-Admin": "1"}
        )
        self.addCleanup(cloud_config._failed_admin_attempts.clear)

    def test_local_proof_required_write_apis_blocked_then_secret_consumed(self):
        self.assertTrue(self.client.get("/api/setup/status").json()["required"])
        secret = cloud_config._read_json(setup.code_file())["code"]
        self.assertNotIn(secret, self.client.get("/api/setup/status").text)
        for path in (
            "/api/admin/login",
            "/api/transport",
            "/api/cloud/write",
            "/api/accounts/restore",
        ):
            self.assertEqual(self.client.post(path, json={}).status_code, 423)
        self.assertEqual(
            self.client.post(
                "/api/setup/complete",
                json={"code": "wrong", "password": "new-test-password"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/setup/complete",
                json={"code": "ungültiger-Code", "password": "new-test-password"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/setup/complete",
                json={"code": secret, "password": "new-test-password"},
            ).status_code,
            200,
        )
        self.assertTrue(cloud_config.verify_admin("new-test-password"))
        self.assertFalse(setup.code_file().exists())
        self.assertEqual(
            self.client.post(
                "/api/setup/complete",
                json={"code": secret, "password": "replacement-password"},
            ).status_code,
            409,
        )
        self.assertTrue(cloud_config.verify_admin("new-test-password"))

    def test_existing_installation_and_accounts_are_not_reinitialized(self):
        cloud_config.set_admin_password("existing-test-password")
        before = cloud_config.ADMIN_FILE.read_bytes()
        setup.initialize()
        self.assertFalse(setup.required())
        self.assertFalse(setup.code_file().exists())
        self.assertEqual(before, cloud_config.ADMIN_FILE.read_bytes())
        cloud_config.ADMIN_FILE.unlink()
        cloud_config._atomic_json(
            cloud_config.STATE_DIR / "users.json",
            {"users": {"named-admin": {"role": "admin"}}},
        )
        setup.initialize()
        self.assertFalse(setup.required())

    def test_plain_http_and_known_default_password_cannot_claim_instance(self):
        setup.initialize()
        client = TestClient(
            app, base_url="http://testserver", headers={"X-FoxAir-Admin": "1"}
        )
        secret = cloud_config._read_json(setup.code_file())["code"]
        self.assertEqual(
            client.post(
                "/api/setup/complete",
                json={"code": secret, "password": "new-test-password"},
            ).status_code,
            403,
        )
        self.assertFalse(cloud_config.ADMIN_FILE.exists())
