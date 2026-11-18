"""Trusted proxy boundaries; all privileged actions are mocked, never live writes."""

import json
import os
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import admin_session, cloud_config
from backend.main import app
from backend.server import TCPPeerApp, main as server_main


class ProxySsoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        directory = Path(self.tmp.name)
        self.config_path = directory / "sso.json"
        self.secret = secrets.token_urlsafe(48)
        self.config = {
            "enabled": True,
            "provider": "authelia",
            "trusted_proxy_ips": ["192.0.2.10"],
            "username_header": "Remote-User",
            "shared_secret_env": "FOXWEB_SSO_SECRET",
            "user_mapping": {"example-user": "admin", "guest": "reader"},
        }
        self.save_config()
        self.patches = [
            patch.object(admin_session, "SESSION_FILE", directory / "sessions.json"),
            patch.object(cloud_config, "ADMIN_FILE", directory / "admin.json"),
            patch.dict(
                os.environ,
                {
                    "FOXAIR_SSO_CONFIG": str(self.config_path),
                    "FOXWEB_SSO_SECRET": self.secret,
                    "FOXAIR_TRUSTED_PROXY_IPS": "192.0.2.10",
                },
            ),
        ]
        for item in self.patches:
            item.start()
        cloud_config.set_admin_password("existing-local-admin-password")
        self.headers = {
            "Remote-User": "example-user",
            "Remote-Name": "Example User",
            "Remote-Email": "example-user@example.invalid",
            "Remote-Groups": "users",
            "X-FoxAir-SSO-Secret": self.secret,
            "X-FoxAir-SSO-Authenticated": "1",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "foxweb.test",
        }
        self.client = TestClient(
            TCPPeerApp(app),
            base_url="https://foxweb.test",
            client=("192.0.2.10", 50000),
        )

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        admin_session._SESSIONS.clear()
        self.tmp.cleanup()

    def save_config(self):
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")

    def state(self, headers=None, client=None):
        return (client or self.client).get(
            "/api/admin/session", headers=self.headers if headers is None else headers
        )

    def assert_reader(self, headers=None, client=None):
        result = self.state(headers, client)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()["authenticated"])
        self.assertEqual(result.json()["role"], "reader")
        self.assertNotIn("foxair_admin_session=", result.headers.get("set-cookie", ""))

    def test_valid_identity_maps_to_existing_admin_and_secure_session(self):
        result = self.state()
        self.assertTrue(result.json()["authenticated"])
        self.assertTrue(result.json()["sso_available"])
        cookie = result.headers["set-cookie"].lower()
        for flag in ("httponly", "secure", "samesite=strict", "max-age=2592000"):
            self.assertIn(flag, cookie)
        self.assertEqual(result.headers["cache-control"], "no-store")
        token = self.client.cookies.get(admin_session.session_cookie_name())
        data = admin_session.session_identity(token)
        self.assertEqual(data["subject"], "example-user")
        self.assertEqual(data["account"], "admin")
        saved = admin_session.SESSION_FILE.read_text()
        self.assertNotIn(token, saved)
        self.assertNotIn(self.secret, saved)
        admin_session._SESSIONS.clear()
        self.assertTrue(self.state().json()["authenticated"])

    def test_unknown_user_groups_and_nonexistent_accounts_do_not_grant_roles(self):
        for user in ("unknown", "admin", "guest"):
            with self.subTest(user=user):
                self.assert_reader(
                    {
                        **self.headers,
                        "Remote-User": user,
                        "Remote-Groups": "admins,superusers",
                    }
                )
        cloud_config.ADMIN_FILE.unlink()
        self.assert_reader()
        self.assertFalse(cloud_config.ADMIN_FILE.exists())

    def test_direct_backend_cannot_spoof_proxy_ip_even_with_correct_secret(self):
        direct = TestClient(
            TCPPeerApp(app),
            base_url="https://foxweb.test",
            client=("192.0.2.88", 50000),
        )
        self.assert_reader(
            {
                **self.headers,
                "X-Forwarded-For": "192.0.2.10",
                "Remote-Addr": "192.0.2.10",
                "Forwarded": "for=192.0.2.10;proto=https",
            },
            direct,
        )
        self.assert_reader({**self.headers, "Remote-User": "admin"}, direct)

    def test_unsupported_server_entry_point_fails_closed(self):
        raw = TestClient(
            app, base_url="https://foxweb.test", client=("192.0.2.10", 50000)
        )
        self.assert_reader(client=raw)

    def test_server_entry_point_disables_all_uvicorn_proxy_rewriting(self):
        with (
            patch("sys.argv", ["server", "--host", "127.0.0.1", "--port", "8081"]),
            patch("backend.server.uvicorn.run") as run,
        ):
            server_main()
        self.assertIs(run.call_args.kwargs["proxy_headers"], False)
        self.assertIsInstance(run.call_args.args[0], TCPPeerApp)

    def test_missing_wrong_secret_and_unconfirmed_auth_are_rejected(self):
        for key, value in (
            ("X-FoxAir-SSO-Secret", "wrong"),
            ("X-FoxAir-SSO-Secret", ""),
            ("X-FoxAir-SSO-Authenticated", ""),
            ("X-FoxAir-SSO-Authenticated", "0"),
        ):
            with self.subTest(key=key, value=value):
                self.assert_reader({**self.headers, key: value})
        with patch.dict(os.environ, {"FOXWEB_SSO_SECRET": "short"}):
            self.assert_reader()

    def test_missing_identity_lan_bypass_and_malformed_identity_stay_readers(self):
        self.assert_reader(
            {key: value for key, value in self.headers.items() if key != "Remote-User"}
        )
        for user in ("", " example-user", "example-user ", "example-user,admin", "example-user\nadmin"):
            with self.subTest(user=repr(user)):
                self.assert_reader({**self.headers, "Remote-User": user})

    def test_duplicate_identity_secret_and_auth_status_are_rejected(self):
        for name in (
            "Remote-User",
            "Remote-Name",
            "Remote-Email",
            "Remote-Groups",
            "X-FoxAir-SSO-Secret",
            "X-FoxAir-SSO-Authenticated",
        ):
            with self.subTest(name=name):
                headers = list(self.headers.items()) + [(name, self.headers[name])]
                self.assert_reader(headers)

    def test_custom_username_header_rejects_conflicting_identity(self):
        self.config["username_header"] = "X-Authelia-User"
        self.save_config()
        self.assert_reader({**self.headers, "X-Authelia-User": "other"})
        self.assertTrue(
            self.state({**self.headers, "X-Authelia-User": "example-user"}).json()[
                "authenticated"
            ]
        )

    def test_disabled_missing_and_bad_config_leave_password_fallback(self):
        for config in (
            {**self.config, "enabled": False},
            {**self.config, "trusted_proxy_ips": ["0.0.0.0/0"]},
            {**self.config, "provider": "other"},
        ):
            self.config_path.write_text(json.dumps(config))
            self.assert_reader()
        self.config_path.write_text("{bad config")
        self.assert_reader()
        self.config_path.unlink()
        self.assert_reader()
        result = self.client.post(
            "/api/admin/login", json={"admin_password": "existing-local-admin-password"}
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(self.state({}).json()["authenticated"])

    def test_sso_cookie_cannot_be_reused_without_current_proxy_identity(self):
        self.state()
        self.assert_reader({})
        direct = TestClient(
            TCPPeerApp(app),
            base_url="https://foxweb.test",
            client=("192.0.2.88", 50000),
        )
        direct.cookies.update(self.client.cookies)
        self.assert_reader(client=direct)
        self.config["enabled"] = False
        self.save_config()
        self.assert_reader()

    def test_identity_mapping_and_secret_changes_revoke_sso_session(self):
        self.state()
        self.assert_reader({**self.headers, "Remote-User": "unknown"})
        self.config["user_mapping"]["example-user"] = "missing-account"
        self.save_config()
        self.assert_reader()
        self.config["user_mapping"]["example-user"] = "admin"
        self.save_config()
        new_secret = secrets.token_urlsafe(48)
        with patch.dict(os.environ, {"FOXWEB_SSO_SECRET": new_secret}):
            with patch(
                "backend.main.create_admin_session",
                side_effect=AssertionError("must not silently mint here"),
            ):
                # Privileged endpoints cannot bootstrap a new session after rotation.
                with patch("backend.main.credentials") as credentials:
                    result = self.client.post(
                        "/api/cloud/account",
                        json={},
                        headers={
                            **self.headers,
                            "X-FoxAir-SSO-Secret": new_secret,
                            "X-FoxAir-Admin": "1",
                        },
                    )
                    self.assertEqual(result.status_code, 403)
                    credentials.assert_not_called()

    def test_logout_persists_reader_state_and_explicit_sso_login_can_resume(self):
        self.state()
        old_token = self.client.cookies.get(admin_session.session_cookie_name())
        headers = {**self.headers, "X-FoxAir-Admin": "1"}
        self.assertEqual(
            self.client.post("/api/admin/logout", headers=headers).status_code, 200
        )
        self.assertFalse(admin_session.authenticated(old_token))
        self.assert_reader()
        result = self.client.post("/api/admin/sso/login", headers=headers)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(self.state().json()["authenticated"])

    def test_api_requires_cookie_custom_header_and_same_origin_after_sso(self):
        self.state()
        with patch(
            "backend.main.credentials", return_value=("user", "secret", "device")
        ) as credentials:
            self.assertEqual(
                self.client.post(
                    "/api/cloud/account", json={}, headers=self.headers
                ).status_code,
                403,
            )
            credentials.assert_not_called()
            bad = {**self.headers, "X-FoxAir-Admin": "1", "Origin": "https://evil.test"}
            self.assertEqual(
                self.client.post(
                    "/api/cloud/account", json={}, headers=bad
                ).status_code,
                403,
            )
            credentials.assert_not_called()
            good = {
                **self.headers,
                "X-FoxAir-Admin": "1",
                "Origin": "https://foxweb.test",
            }
            self.assertEqual(
                self.client.post(
                    "/api/cloud/account", json={}, headers=good
                ).status_code,
                200,
            )
            credentials.assert_called_once()

    def test_sso_login_logout_reject_csrf_and_missing_custom_header(self):
        for path in ("/api/admin/sso/login", "/api/admin/logout"):
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.post(path, headers=self.headers).status_code, 403
                )
                self.assertEqual(
                    self.client.post(
                        path,
                        headers={
                            **self.headers,
                            "X-FoxAir-Admin": "1",
                            "Origin": "https://evil.test",
                        },
                    ).status_code,
                    403,
                )
        self.assert_reader({**self.headers, "Origin": "https://evil.test"})

    def test_read_api_and_sse_keep_existing_guest_behavior(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/register-groups").status_code, 200)
        from backend.routes.lte import lte_events
        from starlette.requests import Request
        import asyncio

        response = asyncio.run(lte_events(Request({"type": "http", "headers": []})))
        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")


class RealTcpPeerTests(unittest.TestCase):
    def test_actual_server_ignores_forwarded_client_ip(self):
        import socket
        import subprocess
        import sys
        import time
        import httpx

        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = directory / "sso.json"
            secret = secrets.token_urlsafe(48)
            config = {
                "enabled": True,
                "provider": "authelia",
                "trusted_proxy_ips": ["127.0.0.1"],
                "user_mapping": {"example-user": "admin"},
            }
            config_path.write_text(json.dumps(config))
            (directory / "admin.json").write_text(
                json.dumps(cloud_config.admin_record("existing-local-admin-password"))
            )
            with socket.socket() as reserve:
                reserve.bind(("127.0.0.1", 0))
                port = reserve.getsockname()[1]
            environment = {
                **os.environ,
                "FOXAIR_STATE_DIR": str(directory),
                "FOXAIR_SSO_CONFIG": str(config_path),
                "FOXWEB_SSO_SECRET": secret,
                "FOXAIR_TRUSTED_PROXY_IPS": "127.0.0.1,192.0.2.10",
                "FORWARDED_ALLOW_IPS": "*",
            }
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "backend.server",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}", timeout=1
                ) as client:
                    for attempt in range(80):
                        try:
                            if client.get("/api/health").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.05)
                    else:
                        self.fail("test server did not start")
                    headers = {
                        "Remote-User": "example-user",
                        "X-FoxAir-SSO-Secret": secret,
                        "X-FoxAir-SSO-Authenticated": "1",
                        "X-Forwarded-Proto": "https",
                        "X-Forwarded-For": "192.0.2.10",
                    }
                    self.assertTrue(
                        client.get("/api/admin/session", headers=headers).json()[
                            "authenticated"
                        ]
                    )
                    config["trusted_proxy_ips"] = ["192.0.2.10"]
                    config_path.write_text(json.dumps(config))
                    self.assertFalse(
                        client.get("/api/admin/session", headers=headers).json()[
                            "authenticated"
                        ]
                    )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
