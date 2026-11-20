import socket
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.bus_connection import BusConnectionManager
from backend.main import app
from backend.settings import Endpoint


class LifecycleTests(unittest.TestCase):
    def test_background_receiving_never_transmits_and_stop_closes_owned_socket(self):
        sock = Mock()
        sock.recv.side_effect = socket.timeout
        endpoint = Endpoint("private", 2001)
        owner = BusConnectionManager(
            endpoint_provider=lambda: endpoint,
            config_provider=lambda: {"connection_mode": "permanent"},
            socket_factory=Mock(return_value=sock),
        )
        owner._receive_once()
        self.assertTrue(owner.connected)
        sock.sendall.assert_not_called()
        self.assertTrue(owner.stop())
        sock.close.assert_called_once()
        self.assertFalse(owner.connected)
        with self.assertRaises(RuntimeError):
            with owner.open(endpoint):
                pass

    def test_start_is_idempotent_and_worker_can_be_stopped_and_restarted(self):
        create = Mock()
        owner = BusConnectionManager(
            endpoint_provider=lambda: None, socket_factory=create
        )
        owner.start()
        first = owner._thread
        owner.start()
        self.assertIs(owner._thread, first)
        self.assertTrue(owner.stop())
        self.assertFalse(first.is_alive())
        owner.start()
        self.assertIsNot(owner._thread, first)
        self.assertTrue(owner.stop())
        create.assert_not_called()

    def test_stop_does_not_close_a_socket_while_an_operation_is_in_flight(self):
        endpoint = Endpoint("private", 2001)
        sock = Mock()
        owner = BusConnectionManager(socket_factory=Mock(return_value=sock))
        entered = threading.Event()
        release = threading.Event()

        def operation():
            with owner.operation(endpoint):
                entered.set()
                release.wait(2)

        worker = threading.Thread(target=operation)
        worker.start()
        self.assertTrue(entered.wait(2))
        self.assertFalse(owner.stop(timeout=0.01))
        sock.close.assert_not_called()
        release.set()
        worker.join(2)
        self.assertTrue(owner.stop())
        sock.close.assert_called_once()

    def test_http_lifespan_starts_receiver_and_stops_scan_before_connection(self):
        calls = []
        with (
            patch("backend.transport_selection.initialize"),
            patch("backend.setup.initialize"),
            patch(
                "backend.bus_connection.start",
                side_effect=lambda: calls.append("start"),
            ),
            patch(
                "backend.register_scan.stop",
                side_effect=lambda: calls.append("scan-stop"),
            ),
            patch(
                "backend.bus_connection.stop",
                side_effect=lambda: calls.append("bus-stop"),
            ),
        ):
            with TestClient(app) as client:
                self.assertTrue(client.get("/api/health").json()["ok"])
                self.assertEqual(calls, ["start"])
        self.assertEqual(calls, ["start", "scan-stop", "bus-stop"])
