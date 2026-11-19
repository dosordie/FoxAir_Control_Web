import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import cloud_config, admin_session, transport_selection as selection
from backend.main import app
from backend.settings import Endpoint


class SharedTransportTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for item in (
            patch.object(cloud_config, "STATE_DIR", root),
            patch.object(cloud_config, "ADMIN_FILE", root / "admin.json"),
            patch.object(admin_session, "SESSION_FILE", root / "sessions.json"),
            patch(
                "backend.settings.display_endpoint",
                return_value=Endpoint("192.168.1.50", 2001, 3),
            ),
            patch(
                "backend.settings.warmlink_endpoint",
                return_value=Endpoint("192.168.1.51", 2001, 99),
            ),
            patch("backend.display_bus.manager.disconnect"),
            patch("backend.bus_connection.manager.disconnect"),
            patch("backend.register_scan.scan.stop"),
        ):
            item.start()
            self.addCleanup(item.stop)

    def test_choice_survives_initialization_and_blocks_other_transport_operations(self):
        self.assertEqual(selection.initialize()["transport"], "display_modbus")
        with selection.operation("display_modbus"):
            pass
        with self.assertRaises(ValueError):
            with selection.operation("warmlink_raw"):
                self.fail("inactive transport reached")
        row = selection.select("cloud")
        self.assertEqual(row["revision"], 2)
        self.assertEqual(selection.initialize(), row)
        self.assertFalse(selection.allows("display_modbus"))

    def test_handover_waits_for_inflight_operation_before_closing_and_publishing(self):
        selection.initialize()
        entered, release, switched = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def operation():
            with selection.operation("display_modbus"):
                entered.set()
                release.wait(2)

        worker = threading.Thread(target=operation)
        worker.start()
        self.assertTrue(entered.wait(1))

        def switch():
            selection.select("cloud")
            switched.set()

        other = threading.Thread(target=switch)
        other.start()
        try:
            self.assertFalse(switched.wait(0.05))
            self.assertEqual(selection.stored()["transport"], "display_modbus")
        finally:
            release.set()
            worker.join(2)
            other.join(2)
        self.assertTrue(switched.is_set())

    def test_only_admin_can_change_choice_and_stale_reader_cannot_activate_other_bus(
        self,
    ):
        cloud_config.set_admin_password("test-only-administrator")
        client = TestClient(
            app, base_url="https://testserver", headers={"X-FoxAir-Admin": "1"}
        )
        self.assertEqual(
            client.get("/api/transport").json()["transport"], "display_modbus"
        )
        self.assertEqual(
            client.post("/api/transport", json={"transport": "cloud"}).status_code, 403
        )
        with patch("socket.create_connection") as socket:
            self.assertEqual(
                client.get("/api/dashboard?transport=warmlink_raw").status_code, 409
            )
            socket.assert_not_called()
        client.post(
            "/api/admin/login", json={"admin_password": "test-only-administrator"}
        )
        self.assertEqual(
            client.post("/api/transport", json={"transport": "cloud"}).json()[
                "revision"
            ],
            2,
        )
        self.assertEqual(client.get("/api/transport").json()["transport"], "cloud")
