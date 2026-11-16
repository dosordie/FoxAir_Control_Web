"""Synthetic stream and actuator tests; no sockets to the heat pump."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import socket
import unittest
from unittest.mock import Mock, patch

from backend import settings, warmlink
from backend.rtu import with_crc
from backend.settings import Endpoint
from backend.warmlink_frames import find_frames
from backend.cloud_write import WriteConflictError, WriteValidationError


def read_request(reg=1158):
    return with_crc(b"\x63\x03" + reg.to_bytes(2, "big") + b"\x00\x01")


def response(value=350):
    return with_crc(b"\x63\x03\x02" + value.to_bytes(2, "big"))


class LteStreamTests(unittest.TestCase):
    def test_fragmented_fc16_keeps_embedded_headers_inside_block(self):
        words = b"\x63\x03" * 90
        frame = with_crc(bytes.fromhex("63 10 07 d1 00 5a b4") + words)
        buf = bytearray(frame[:90])
        self.assertEqual(find_frames(buf, 125), [])
        buf.extend(frame[90:] + response())
        frames = find_frames(buf, 125)
        self.assertEqual([f[9] for f in frames], ["word-frame", "read-response"])
        self.assertEqual(frames[0][6], frame)

    def test_fragmented_echo_and_foreign_blocks_do_not_replace_readback(self):
        sock = Mock()
        echo = read_request()
        block = with_crc(bytes.fromhex("63 10 07 d1 00 01 02 00 00"))
        data = echo + block + response()
        sock.recv.side_effect = [data[:4], data[4:13], data[13:]]
        client = warmlink.WarmlinkSession(sock, Endpoint("private", 1))
        with patch.object(client, "quiet"):
            self.assertEqual(client.read_holding(1158), [350])
        sock.sendall.assert_called_once_with(echo)

    def test_competing_fc03_aborts_and_poisoned_session_cannot_continue(self):
        sock = Mock()
        sock.recv.return_value = read_request(2045) + response()
        client = warmlink.WarmlinkSession(sock, Endpoint("private", 1))
        with patch.object(client, "quiet"):
            with self.assertRaisesRegex(ValueError, "Konkurrierende"):
                client.read_holding(1158)
        with self.assertRaisesRegex(ValueError, "gesperrt"):
            client.read_holding(2045)
        sock.sendall.assert_called_once()

    def test_write_ack_requires_address_and_quantity(self):
        sock = Mock()
        wrong = with_crc(bytes.fromhex("63 10 04 87 00 01"))
        correct = with_crc(bytes.fromhex("63 10 04 86 00 01"))
        sock.recv.side_effect = [wrong, correct]
        client = warmlink.WarmlinkSession(sock, Endpoint("private", 1))
        with patch.object(client, "quiet"):
            client.write_one(1158, 355)
        self.assertEqual(sock.recv.call_count, 2)
        sock.sendall.assert_called_once_with(with_crc(bytes.fromhex("63 10 04 86 00 01 02 01 63")))

    def test_quiet_wait_does_not_send_over_unanswered_dtu_request(self):
        sock = Mock()
        sock.recv.side_effect = [read_request(2045)] + [socket.timeout()] * 20
        client = warmlink.WarmlinkSession(sock, Endpoint("private", 1, timeout=5))
        ticks = iter(i * .05 for i in range(200))
        with patch("backend.warmlink.time.monotonic", side_effect=lambda: next(ticks)):
            with self.assertRaisesRegex(ValueError, "unbeantwortet"):
                client.read_holding(1158)
        sock.sendall.assert_not_called()

    def test_crc_error_is_not_a_valid_frame(self):
        data = bytearray(response())
        data[-1] ^= 128
        self.assertEqual(find_frames(data, 125), [])


class LteWriteTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        @contextmanager
        def connection(endpoint):
            yield self.client
        self.patches = [patch("backend.warmlink.open_warmlink", connection),
                        patch("backend.settings.warmlink_endpoint", return_value=Endpoint("private", 2001)),
                        patch("backend.warmlink.time.sleep"), patch.object(warmlink, "_last_write", {})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def test_r02_scales_only_the_local_wire_value_and_reads_back(self):
        self.client.read_holding.side_effect = [[350], [250, 550], [355]]
        result = warmlink.write_control("R02", "35.5", "35")
        self.assertTrue(result["confirmed"])
        self.client.write_one.assert_called_once_with(1158, 355)
        self.assertEqual(result["value"], 35.5)

    def test_conflict_and_bounds_send_nothing(self):
        self.client.read_holding.side_effect = [[360]]
        with self.assertRaises(WriteConflictError):
            warmlink.write_control("R02", 40, 35)
        self.client.read_holding.side_effect = [[350], [250, 390]]
        with self.assertRaises(WriteValidationError):
            warmlink.write_control("R02", 40, 35)
        self.client.write_one.assert_not_called()

    def test_unclear_write_not_retried(self):
        self.client.read_holding.return_value = [1]
        self.client.write_one.side_effect = TimeoutError()
        self.assertFalse(warmlink.write_control("Mode", 2, 1)["confirmed"])
        self.client.write_one.assert_called_once()
        self.client.read_holding.assert_called_once()


class LteConfigurationTests(unittest.TestCase):
    def test_config_is_disabled_by_default_and_saved_privately(self):
        with TemporaryDirectory() as directory, patch.object(settings, "WARMLINK_FILE", Path(directory) / "lte.json"):
            self.assertIsNone(settings.warmlink_endpoint())
            settings.save_warmlink("192.168.1.50", 2001, True)
            self.assertEqual(settings.warmlink_endpoint().port, 2001)
            for host in ("https://example.org", "8.8.8.8", "127.0.0.1", "0.0.0.0"):
                with self.assertRaises(ValueError):
                    settings.save_warmlink(host, 2001, True)
