import unittest
from unittest.mock import Mock, patch

from backend.bus_stream import BusOpenError, ModbusResponseTimeout
from backend.rtu import RtuReadSession, StandardConnection
from backend.settings import Endpoint


class StandardConnectionTests(unittest.TestCase):
    def test_browser_lease_reuses_socket_and_discards_failed_exchange(self):
        manager = StandardConnection()
        self.addCleanup(manager.disconnect)
        endpoint = Endpoint("192.0.2.42", 2001)
        first, second = Mock(), Mock()
        with patch(
            "backend.rtu.socket.create_connection", side_effect=[first, second]
        ) as connect:
            manager.lease(90)
            with manager.session(endpoint) as session:
                self.assertIs(session.sock, first)
            first.close.assert_not_called()
            with manager.session(endpoint) as session:
                self.assertIs(session.sock, first)
                first.recv.side_effect = TimeoutError
                # A caller can handle the error and retain values from earlier blocks.
                with self.assertRaisesRegex(ModbusResponseTimeout, 'TCP verbunden.*Verbindungskonflikt'):
                    session.read_holding(1001)
            first.close.assert_called_once()
            self.assertEqual(connect.call_count, 1)
            with manager.session(endpoint) as session:
                self.assertIs(session.sock, second)
                expiry = manager._expiry
            with patch("backend.rtu.time.monotonic", return_value=manager._until + 1):
                manager._expire(expiry)
            expiry.cancel()
            second.close.assert_called_once()

    def test_without_a_browser_socket_closes_after_request(self):
        manager = StandardConnection()
        endpoint = Endpoint("192.0.2.42", 2001)
        with patch("backend.rtu.socket.create_connection") as connect:
            with manager.session(endpoint):
                pass
            connect.return_value.close.assert_called_once()


    def test_tcp_connection_failures_are_distinct_and_logged_without_socket_details(self):
        endpoint = Endpoint("192.0.2.42", 2001)
        failures = (
            (ConnectionRefusedError("private details"), "TCP-Verbindung abgelehnt"),
            (TimeoutError("private details"), "TCP-Verbindungsaufbau"),
        )
        for error, message in failures:
            with self.subTest(error=type(error).__name__):
                with (
                    patch("backend.rtu.socket.create_connection", side_effect=error),
                    patch("backend.bus_stream.log_event") as log,
                    self.assertRaisesRegex(BusOpenError, message) as raised,
                ):
                    with StandardConnection().session(endpoint):
                        self.fail("The session must not open")
                self.assertNotIn("private details", str(raised.exception))
                log.assert_called_once_with("standard-error", str(raised.exception))

    def test_serial_reply_timeout_does_not_report_a_tcp_conflict(self):
        sock = Mock()
        sock.recv.side_effect = TimeoutError
        with self.assertRaises(ModbusResponseTimeout) as raised:
            RtuReadSession(sock, 1, medium="serial").read_holding(1001)
        self.assertNotIn("TCP", str(raised.exception))
        self.assertNotIn("Verbindungskonflikt", str(raised.exception))
