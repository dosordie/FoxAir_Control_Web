"""Protocol replay tests; never open a physical heat-pump connection."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.display_protocol import DisplayProtocol, REQUIRED, valid_packet
from backend.rtu import with_crc
from backend import settings, cloud_config, admin_session
from backend.main import app


def ack(address, unit=3):
    return with_crc(bytes((unit, 16)) + address.to_bytes(2, "big") + b"\x00\x01")


def packet(start, unit=3, marker=528):
    words = [0] * 90
    raw = b"WF0000000000"
    words[:6] = [int.from_bytes(raw[n : n + 2], "big") for n in range(0, 12, 2)]
    words[8] = marker
    words[9] = start
    words[10] = 1
    payload = b"".join(w.to_bytes(2, "big") for w in words)
    return with_crc(
        bytes((unit, 16)) + start.to_bytes(2, "big") + b"\x00\x5a\xb4" + payload
    )


class DisplayProtocolTests(TestCase):
    def setUp(self):
        self.now = 0
        self.words = []
        self.protocol = DisplayProtocol(
            lambda start, words: self.words.append((start, words)), lambda: self.now
        )

    def test_idle_is_strictly_passive_and_invalid_packets_are_ignored(self):
        self.now = 1
        self.assertIsNone(self.protocol.tick())
        self.protocol.feed(packet(1001, marker=0))
        damaged = bytearray(packet(1001))
        damaged[-1] ^= 1
        self.protocol.feed(damaged)
        self.assertEqual(self.words, [])
        self.protocol.feed(packet(1001, unit=1))
        self.assertEqual(self.words, [])
        self.protocol.feed(packet(2001, unit=0))
        self.assertEqual(self.words[0][0], 2001)

    def test_snapshot_uses_only_the_two_fixed_ack_gated_commands(self):
        self.protocol.start()
        self.now = 0.5
        prepare = self.protocol.tick()
        self.assertEqual(prepare[2:4], b"\x51\x12")
        self.assertEqual(prepare[7:9], b"\x00\x00")
        self.now = 0.6
        self.protocol.feed(prepare)  # TX echo is not an ACK.
        self.now = 1.5
        self.assertIsNone(self.protocol.tick())
        self.protocol.feed(ack(0x5112, unit=1))
        self.assertEqual(self.protocol.phase, "wait_prepare")
        self.protocol.feed(ack(0x5112))
        self.now = 2
        flag = self.protocol.tick()
        self.assertEqual(flag[2:4], b"\x0b\xc3")
        self.assertEqual(flag[7:9], b"\x80\x00")
        self.now = 2.1
        self.protocol.feed(ack(0x0BC3))
        for start in REQUIRED:
            self.protocol.feed(packet(start))
        self.assertEqual(self.protocol.sync["status"], "complete")
        self.assertEqual(self.protocol.sync["completed"], 6)
        self.assertIsNone(self.protocol.tick())

    def test_fragmented_packets_keep_payload_and_complete_only_fresh_blocks(self):
        data = packet(1091)
        for byte in data:
            self.protocol.feed(bytes([byte]))
        self.assertEqual(len(self.words), 1)
        self.protocol.start()
        self.now = 1
        self.protocol.tick()
        self.protocol.feed(ack(0x5112))
        self.now = 2
        self.protocol.tick()
        self.now = 3
        self.protocol.feed(packet(1001))
        self.assertEqual(self.protocol.sync["completed"], 1)
        self.assertNotIn(1091, self.protocol.sync["received"])

    def test_retry_is_bounded_without_arbitrary_writes(self):
        self.protocol.start()
        transmissions = []
        for n in range(500):
            self.now = n * 0.5
            command = self.protocol.tick()
            if command:
                transmissions.append(command)
        self.assertEqual(self.protocol.sync["status"], "error")
        self.assertLessEqual(len(transmissions), 9)
        self.assertTrue(all(c[2:4] == b"\x51\x12" for c in transmissions))

    def test_overlapping_passive_reads_are_not_mapped_to_main(self):
        query = with_crc(b"\x03\x03\x0b\xb9\x00\x15")
        self.protocol.feed(query)
        self.now = 0.1
        self.protocol.feed(query)
        words = [0] * 21
        words[10] = 0x8000
        response = with_crc(
            b"\x03\x03\x2a" + b"".join(w.to_bytes(2, "big") for w in words)
        )
        self.protocol.feed(response)
        self.assertIsNone(self.protocol.flag)
        self.assertEqual(self.words, [])


class LocalConfigTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            patch.object(settings, "STATE_DIR", self.root),
            patch.object(settings, "WARMLINK_FILE", self.root / "warmlink.json"),
            patch.object(cloud_config, "STATE_DIR", self.root),
            patch.object(cloud_config, "ADMIN_FILE", self.root / "admin.json"),
            patch.object(admin_session, "SESSION_FILE", self.root / "sessions.json"),
        ]
        for p in self.patches:
            p.start()
        cloud_config.set_admin_password("test-only-administrator")
        self.client = TestClient(
            app, base_url="https://testserver", headers={"X-FoxAir-Admin": "1"}
        )

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_configuration_requires_admin_and_keeps_disabled_default(self):
        self.assertIsNone(settings.display_endpoint())
        self.assertEqual(
            self.client.post("/api/local/display_modbus/config", json={}).status_code,
            403,
        )
        self.client.post(
            "/api/admin/login", json={"admin_password": "test-only-administrator"}
        )
        row = {
            "host": "192.168.1.50",
            "port": 2001,
            "slave": 3,
            "timeout": 2,
            "enabled": False,
            "connection_mode": "browser",
        }
        self.assertEqual(
            self.client.post(
                "/api/local/display_modbus/config/save", json=row
            ).status_code,
            200,
        )
        self.assertIsNone(settings.display_endpoint())
        self.assertEqual(
            self.client.post(
                "/api/local/display_modbus/config/save", json={**row, "slave": 99}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/api/local/display_modbus/config/save",
                json={**row, "host": "8.8.8.8", "enabled": True},
            ).status_code,
            422,
        )

    def test_endpoint_collision_is_rejected_in_both_directions(self):
        settings.save_local_bus("display_modbus", "192.168.1.50", 2001, True)
        with self.assertRaises(ValueError):
            settings.save_warmlink("192.168.1.50", 2001, True)
        with self.assertRaises(ValueError):
            settings.save_local_bus(
                "standard_modbus", "192.168.1.50", 2001, True, slave=99
            )

    def test_normal_display_writes_are_rejected_without_opening_any_socket(self):
        self.client.post(
            "/api/admin/login", json={"admin_password": "test-only-administrator"}
        )
        with patch("socket.create_connection") as connection:
            result = self.client.post(
                "/api/parameters/1158/write",
                json={"transport": "display_modbus", "value": "35", "expected": "34"},
            )
            self.assertIn(result.status_code, (409, 422))
            connection.assert_not_called()


class DisplayTcpTests(TestCase):
    def test_real_tcp_passive_reception_then_explicit_snapshot(self):
        import socket, threading, time
        from backend.display_bus import DisplayBus
        from backend.settings import Endpoint

        received = []
        writes = []
        failures = []
        stop = threading.Event()
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(3)
        endpoint = Endpoint("127.0.0.1", listener.getsockname()[1], 3, 1)

        def peer():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(3)
                    live = packet(2001, unit=0)
                    connection.sendall(live[:11])
                    connection.sendall(live[11:])
                    for expected in (0x5112, 0x0BC3):
                        data = bytearray()
                        while len(data) < 11:
                            chunk = connection.recv(11 - len(data))
                            if not chunk:
                                raise RuntimeError("client closed")
                            data.extend(chunk)
                        writes.append(bytes(data))
                        if int.from_bytes(data[2:4], "big") != expected:
                            raise AssertionError("unexpected write")
                        connection.sendall(ack(expected))
                    connection.sendall(b"".join(packet(start) for start in REQUIRED))
                    stop.wait(3)
            except Exception as error:
                failures.append(str(error))

        thread = threading.Thread(target=peer, daemon=True)
        thread.start()
        bus = DisplayBus()
        config = {
            "enabled": True,
            "connection_mode": "permanent",
            "browser_timeout_seconds": 90,
        }
        with (
            patch("backend.display_bus.display_endpoint", return_value=endpoint),
            patch("backend.display_bus.local_bus_config", return_value=config),
            patch(
                "backend.display_bus.remember_words",
                side_effect=lambda e, start, words, **kw: received.append(
                    (start, words)
                ),
            ),
        ):
            try:
                bus.start()
                deadline = time.monotonic() + 3
                while not received and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertEqual(received[0][0], 2001)
                self.assertEqual(writes, [], "passive connection must not transmit")
                bus.synchronize()
                deadline = time.monotonic() + 5
                while (
                    bus.state()["scan"]["status"] == "running"
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)
                self.assertEqual(bus.state()["scan"]["status"], "complete")
                self.assertEqual(len(writes), 2)
            finally:
                stop.set()
                bus.stop()
                listener.close()
                thread.join(timeout=3)
        self.assertEqual(failures, [])

    def test_disconnect_reconnects_passively_without_replaying_trigger(self):
        import socket, threading, time
        from backend.display_bus import DisplayBus
        from backend.settings import Endpoint

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        listener.settimeout(5)
        endpoint = Endpoint("127.0.0.1", listener.getsockname()[1], 3, 1)
        connected_again = threading.Event()
        stop = threading.Event()
        writes = []
        failures = []

        def peer():
            try:
                first, _ = listener.accept()
                with first:
                    first.settimeout(3)
                    data = bytearray()
                    while len(data) < 11:
                        chunk = first.recv(11 - len(data))
                        if not chunk:
                            raise RuntimeError("client closed")
                        data.extend(chunk)
                    writes.append(bytes(data))
                second, _ = listener.accept()
                with second:
                    second.settimeout(0.4)
                    connected_again.set()
                    try:
                        writes.append(second.recv(11))
                    except socket.timeout:
                        pass
                    stop.wait(2)
            except Exception as error:
                failures.append(str(error))

        thread = threading.Thread(target=peer, daemon=True)
        thread.start()
        bus = DisplayBus()
        config = {"connection_mode": "permanent", "browser_timeout_seconds": 90}
        with (
            patch("backend.display_bus.display_endpoint", return_value=endpoint),
            patch("backend.display_bus.local_bus_config", return_value=config),
        ):
            try:
                bus.start()
                deadline = time.monotonic() + 2
                while not bus.state()["connected"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                bus.synchronize()
                self.assertTrue(connected_again.wait(5))
                time.sleep(0.5)
                self.assertTrue(bus.thread.is_alive())
                self.assertEqual(bus.state()["scan"]["status"], "idle")
                self.assertEqual(len(writes), 1)
                self.assertEqual(writes[0][2:4], b"\x51\x12")
            finally:
                stop.set()
                bus.stop()
                listener.close()
                thread.join(timeout=3)
        self.assertEqual(failures, [])


class DisplayProjectionTests(TestCase):
    def test_live_selected_target_is_present_without_parameter_snapshot(self):
        from backend.routes.local_buses import local_snapshot

        row = {
            "register": 2014,
            "raw": 366,
            "value": 36.6,
            "unit": "°C",
            "quality": "observed",
            "transport": "display_modbus",
            "timestamp": "2026-11-19T20:00:00+00:00",
        }
        with (
            patch(
                "backend.routes.local_buses.manager.values", return_value={"2014": row}
            ),
            patch(
                "backend.routes.local_buses.manager.state",
                return_value={"connected": True, "scan": {}},
            ),
            patch("backend.last_values.store.values", return_value={}),
        ):
            target = local_snapshot()["metrics"]["target"]
        self.assertEqual(target["value"], 36.6)
        self.assertEqual(target["source_code"], "2014")
        self.assertEqual(target["quality"], "observed")

    def test_live_selected_target_wins_over_fresh_base_target(self):
        from backend.routes.local_buses import local_snapshot

        row = {
            "register": 2014,
            "value": 36.6,
            "unit": "°C",
            "quality": "observed",
            "timestamp": "2026-11-19T20:00:00+00:00",
        }
        base = {**row, "register": 1158, "value": 35}
        with (
            patch(
                "backend.routes.local_buses.manager.values",
                return_value={"2014": row, "1158": base},
            ),
            patch(
                "backend.routes.local_buses.manager.state",
                return_value={"connected": True, "scan": {}},
            ),
            patch("backend.last_values.store.values", return_value={}),
        ):
            metrics = local_snapshot()["metrics"]
        self.assertEqual(metrics["target"]["value"], 36.6)
        self.assertEqual(metrics["base_target"]["value"], 35)

    def test_live_power_state_does_not_wait_for_parameter_packet(self):
        from backend.routes.local_buses import local_snapshot

        row = {
            "register": 2011,
            "raw": 1,
            "value": "Ein",
            "unit": "",
            "quality": "observed",
            "timestamp": "2026-11-19T20:00:00+00:00",
        }
        with (
            patch(
                "backend.routes.local_buses.manager.values", return_value={"2011": row}
            ),
            patch(
                "backend.routes.local_buses.manager.state",
                return_value={"connected": True, "scan": {}},
            ),
            patch("backend.last_values.store.values", return_value={}),
        ):
            snapshot = local_snapshot()
        self.assertEqual(snapshot["metrics"]["power"]["value"], "Ein")
        self.assertEqual(snapshot["values"]["2011"]["name"], "Gerätezustand")
