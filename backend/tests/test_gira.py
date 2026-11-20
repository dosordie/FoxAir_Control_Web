import asyncio
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, IsolatedAsyncioTestCase
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import gira, cloud_config, admin_session
from backend.main import app


class GiraProtocolTests(TestCase):
    def test_subscription_ack_and_push_preserve_zero_and_text_but_ignore_other_keys(
        self,
    ):
        allowed = {"co@1", "co@2"}
        ack = {
            "type": "subscribe",
            "data": {
                "items": [
                    {"key": "CO@1", "code": 0, "data": {"value": "0"}},
                    {"key": "CO@2", "code": 0, "value": "Heizkreis aktiv"},
                ]
            },
        }
        self.assertEqual(
            gira.updates(ack, allowed), {"co@1": 0, "co@2": "Heizkreis aktiv"}
        )
        self.assertEqual(
            gira.updates(
                {"subscription": {"key": "CO@2"}, "data": {"value": "Text"}}, allowed
            ),
            {"co@2": "Text"},
        )
        self.assertEqual(
            gira.updates(
                {"data": [{"uid": 1, "value": 2.5}, {"uid": 99, "value": 100}]}, allowed
            ),
            {"co@1": 2.5},
        )
        self.assertEqual(gira.updates({"code": 403, "data": {"CO@1": 42}}, allowed), {})
        self.assertEqual(
            gira.updates(
                {"subscription": None, "data": {"CO@1": {"value": 4}}}, allowed
            ),
            {"co@1": 4},
        )

    def test_gira_base64_text_and_numeric_values(self):
        self.assertEqual(gira.scalar("SGVpemVu"), "Heizen")
        text = "ein seit 5h:11m"
        self.assertEqual(gira.scalar(base64.b64encode(text.encode()).decode()), text)
        self.assertEqual(gira.scalar("0"), 0)
        self.assertEqual(gira.scalar("Heizkreis aktiv"), "Heizkreis aktiv")
        self.assertEqual(gira.scalar("SGVpemVu", "plain"), "SGVpemVu")
        self.assertEqual(
            gira.scalar(
                base64.b64encode("Kühlen".encode("latin-1")).decode(), "latin1"
            ),
            "Kühlen",
        )

    def test_admin_only_configuration_never_returns_password_and_preserves_it_on_blank_save(
        self,
    ):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with (
                patch.object(cloud_config, "STATE_DIR", root),
                patch.object(cloud_config, "ADMIN_FILE", root / "admin.json"),
                patch.object(admin_session, "SESSION_FILE", root / "sessions.json"),
            ):
                cloud_config.set_admin_password("test-only-administrator")
                client = TestClient(
                    app, base_url="https://testserver", headers={"X-FoxAir-Admin": "1"}
                )
                self.assertEqual(
                    client.post("/api/expert/gira/config", json={}).status_code, 403
                )
                client.post(
                    "/api/admin/login",
                    json={"admin_password": "test-only-administrator"},
                )
                row = {
                    "enabled": True,
                    "host": "192.168.1.50",
                    "username": "test",
                    "password": "test-only-secret",
                    "objects": [{"key": "1", "name": "PV", "unit": "kW"}],
                }
                self.assertEqual(
                    client.post("/api/expert/gira/save", json=row).status_code, 200
                )
                private = client.post("/api/expert/gira/config", json={}).json()
                self.assertEqual(private["password"], "")
                self.assertTrue(private["password_configured"])
                self.assertEqual(private["objects"][0]["key"], "CO@1")
                self.assertEqual(
                    client.post(
                        "/api/expert/gira/save", json={**row, "password": ""}
                    ).status_code,
                    200,
                )
                self.assertEqual(gira.config()["password"], "test-only-secret")
                public = client.get("/api/expert/gira/state").text
                self.assertNotIn("test-only-secret", public)
                self.assertNotIn("192.168.1.50", public)
                self.assertNotIn("CO@1", public)
                self.assertEqual(
                    client.post(
                        "/api/expert/gira/save", json={**row, "host": "8.8.8.8"}
                    ).status_code,
                    422,
                )

                archive = client.post(
                    "/api/accounts/backup",
                    json={"password": "test-only-backup-password"},
                ).json()["archive"]
                self.assertNotIn("test-only-secret", archive)
                old_revision = gira.config()["revision"]
                restored = client.post(
                    "/api/accounts/restore",
                    json={"password": "test-only-backup-password", "archive": archive},
                )
                self.assertEqual(restored.status_code, 200)
                self.assertEqual(gira.config()["password"], "test-only-secret")
                self.assertNotEqual(gira.config()["revision"], old_revision)


class GiraSocketTests(IsolatedAsyncioTestCase):
    async def test_real_websocket_only_sends_subscription_and_receives_numeric_and_text_values(
        self,
    ):
        from websockets.asyncio.server import serve

        sent = []
        finished = asyncio.Event()

        async def peer(ws):
            self.assertIn("authorization=", ws.request.path)
            sent.append(json.loads(await ws.recv()))
            await ws.send(
                json.dumps(
                    {
                        "type": "subscribe",
                        "data": {
                            "items": [
                                {"key": "CO@1", "value": 0},
                                {"key": "CO@2", "value": "Textwert"},
                            ]
                        },
                    }
                )
            )
            await finished.wait()

        async with serve(peer, "127.0.0.1", 0) as server:
            cfg = {
                **gira.Config().model_dump(),
                "enabled": True,
                "host": "127.0.0.1",
                "port": server.sockets[0].getsockname()[1],
                "username": "test",
                "password": "test-only",
                "revision": "simulated",
                "objects": [
                    {"key": "CO@1", "name": "Zahl", "unit": ""},
                    {"key": "CO@2", "name": "Text", "unit": ""},
                ],
            }
            client = gira.GiraClient()
            with patch("backend.gira.config", return_value=cfg):
                try:
                    client.start()
                    for _ in range(100):
                        if len(client.values) == 2:
                            break
                        await asyncio.sleep(0.01)
                    self.assertEqual(client.snapshot()["items"][0]["value"], 0)
                    self.assertEqual(client.snapshot()["items"][1]["value"], "Textwert")
                    self.assertEqual(
                        sent,
                        [{"type": "subscribe", "param": {"keys": ["CO@1", "CO@2"]}}],
                    )
                    cfg["enabled"] = False
                    cfg["revision"] = "disabled"
                    self.assertEqual(client.snapshot()["items"], [])
                finally:
                    finished.set()
                    await client.stop()
