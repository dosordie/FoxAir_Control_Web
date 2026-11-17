import asyncio
from contextlib import contextmanager
import json
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

from backend import bus_connection as bus, register_scan as scan
from backend.routes.lte import lte_events, lte_snapshot
from backend.register_definitions import (
    LTE_DASHBOARD_BLOCKS as LTE_READ_BLOCKS,
    DASHBOARD_FIELDS,
)
from backend.rtu import with_crc
from backend.settings import Endpoint
from backend.register_cache import RegisterCache
from backend.warmlink import WarmlinkSession


class BlockReadTests(unittest.TestCase):
    def test_correlated_foreign_fc03_is_observed_but_not_a_readback(self):
        endpoint = Endpoint("private", 2001)
        cache = RegisterCache()
        cache.select_source(endpoint)
        request = with_crc(bytes.fromhex("63 03 07 fe 00 01"))
        response = with_crc(bytes.fromhex("63 03 02 01 7d"))
        sock = Mock()
        sock.recv.side_effect = [request, response]
        client = WarmlinkSession(
            sock,
            endpoint,
            on_observed_read=lambda start, words: cache.record(
                endpoint, start, words, observed=True
            ),
        )
        client.receive(0.1)
        self.assertEqual(client.foreign_pending, (2046, 1))
        client.receive(0.1)
        self.assertIsNone(client.foreign_pending)
        self.assertEqual(cache.values(endpoint, connected=True)["2046"]["value"], 38.1)
        self.assertEqual(
            cache.values(endpoint, connected=True)["2046"]["quality"], "observed"
        )
        sock.sendall.assert_not_called()

    def test_overlapping_foreign_reads_cannot_become_measurements(self):
        endpoint = Endpoint("private", 2001)
        request = with_crc(bytes.fromhex("63 03 07 fe 00 01"))
        other = with_crc(bytes.fromhex("63 03 07 fd 00 01"))
        response = with_crc(bytes.fromhex("63 03 02 01 7d"))
        sock = Mock()
        sock.recv.return_value = request + other + response
        observer = Mock()
        client = WarmlinkSession(sock, endpoint, on_observed_read=observer)
        client.receive(0.1)
        self.assertTrue(client.foreign_ambiguous)
        observer.assert_not_called()

    def test_expired_ambiguous_request_does_not_block_a_later_read(self):
        import socket

        endpoint = Endpoint("private", 2001, timeout=5)
        sock = Mock()
        response = with_crc(bytes.fromhex("63 03 02 01 7d"))

        def receive(_size):
            if sock.sendall.called:
                return response
            raise socket.timeout()

        sock.recv.side_effect = receive
        observer = Mock()
        client = WarmlinkSession(sock, endpoint, on_observed_read=observer)
        client.foreign_pending = (6, 1)
        client.foreign_since = 10
        client.foreign_ambiguous = True
        ticks = iter(100 + i * 0.05 for i in range(200))
        with patch(
            "backend.warmlink_protocol.time.monotonic", side_effect=lambda: next(ticks)
        ):
            self.assertEqual(client.read_holding(2046, 1), [381])
        self.assertIsNone(client.foreign_pending)
        self.assertFalse(client.foreign_ambiguous)
        observer.assert_not_called()
        sock.sendall.assert_called_once()

    def test_expiration_never_assigns_a_late_response_to_an_old_request(self):
        endpoint = Endpoint("private", 2001, timeout=5)
        sock = Mock()
        sock.recv.return_value = with_crc(bytes.fromhex("63 03 02 01 7d"))
        observer = Mock()
        client = WarmlinkSession(sock, endpoint, on_observed_read=observer)
        client.foreign_pending = (2046, 1)
        client.foreign_since = 10
        with patch("backend.warmlink_protocol.time.monotonic", return_value=16):
            client.receive(0.1)
        observer.assert_not_called()
        self.assertIsNone(client.foreign_pending)
        sock.sendall.assert_not_called()

    def test_wire_read_uses_fc03_and_ninety_words(self):
        words = list(range(90))
        response = with_crc(
            b"\x63\x03\xb4" + b"".join(word.to_bytes(2, "big") for word in words)
        )
        sock = Mock()
        sock.recv.side_effect = [response[:19], response[19:]]
        client = WarmlinkSession(sock, Endpoint("private", 2001))
        with patch.object(client, "quiet"):
            self.assertEqual(client.read_holding(1001, 90), words)
        sock.sendall.assert_called_once_with(
            with_crc(bytes.fromhex("63 03 03 e9 00 5a"))
        )

    def test_dashboard_blocks_cover_needed_words_with_at_most_ninety_per_read(self):
        covered = {
            reg
            for start, count in LTE_READ_BLOCKS
            for reg in range(start, start + count)
        }
        self.assertTrue(set(DASHBOARD_FIELDS.values()) | {2014} <= covered)
        self.assertEqual(len(LTE_READ_BLOCKS), 3)
        self.assertTrue(all(0 < count <= 90 for _, count in LTE_READ_BLOCKS))


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.endpoint = Endpoint("private", 2001)
        self.client = Mock()
        self.client.read_holding.side_effect = lambda start, count: list(range(count))

        @contextmanager
        def connection(endpoint):
            yield self.client

        self.provider = Mock(return_value=self.endpoint)
        self.owner = scan.RegisterScan(
            endpoint_provider=self.provider, connection_factory=connection
        )
        self.thread_errors = []
        self.thread_hook = patch(
            "threading.excepthook",
            side_effect=lambda error: self.thread_errors.append(error.exc_value),
        )
        self.thread_hook.start()

    def tearDown(self):
        self.owner.stop()
        self.thread_hook.stop()
        self.assertEqual(self.thread_errors, [])

    def run_scan(self):
        result = self.owner.start()
        self.assertTrue(result["started"])
        self.owner._thread.join(2)
        self.assertFalse(self.owner._thread.is_alive())

    def test_all_eight_blocks_are_sequential_and_complete(self):
        self.run_scan()
        self.assertEqual(
            self.client.read_holding.call_args_list,
            [
                call(start, 90)
                for start in (1001, 1091, 1181, 1271, 1361, 1451, 2001, 2091)
            ],
        )
        self.assertEqual(self.owner.status()["status"], "complete")
        self.assertEqual(self.owner.status()["completed"], 8)
        self.client.write_one.assert_not_called()

    def test_first_unclear_response_aborts_without_retry(self):
        self.client.read_holding.side_effect = [
            list(range(90)),
            TimeoutError("private response"),
        ]
        self.run_scan()
        self.assertEqual(self.owner.status()["status"], "partial")
        self.assertEqual(self.owner.status()["completed"], 1)
        self.assertEqual(self.client.read_holding.call_count, 2)
        self.assertNotIn("private response", self.owner.status()["error"])

    def test_multiple_tabs_share_running_or_recent_job(self):
        import threading

        entered = threading.Event()
        release = threading.Event()

        def slow_read(start, count):
            entered.set()
            release.wait(2)
            return list(range(count))

        self.client.read_holding.side_effect = slow_read
        self.owner.start()
        self.assertTrue(entered.wait(2))
        try:
            self.assertFalse(self.owner.start()["started"])
        finally:
            release.set()
        self.owner._thread.join(2)
        self.assertEqual(self.owner.status()["status"], "complete")
        self.assertFalse(self.owner.start()["started"])
        self.assertEqual(self.client.read_holding.call_count, 8)

    def test_configuration_change_aborts_before_next_transmission(self):
        changed = [False]
        self.provider.side_effect = lambda: None if changed[0] else self.endpoint

        def read(start, count):
            changed[0] = True
            return list(range(count))

        self.client.read_holding.side_effect = read
        self.run_scan()
        self.assertEqual(self.client.read_holding.call_count, 1)

    def test_shutdown_stops_before_sending_the_next_block(self):
        import threading

        entered = threading.Event()
        release = threading.Event()

        def slow_read(start, count):
            entered.set()
            release.wait(2)
            return list(range(count))

        self.client.read_holding.side_effect = slow_read
        self.owner.start()
        self.assertTrue(entered.wait(2))
        self.assertFalse(self.owner.stop(timeout=0.01))
        release.set()
        self.assertTrue(self.owner.stop(timeout=2))
        self.assertEqual(self.client.read_holding.call_count, 1)
        self.assertEqual(self.owner.status()["status"], "partial")


class CacheTests(unittest.TestCase):
    def test_headers_and_virtual_ids_never_reach_browser_and_latest_source_wins(self):
        endpoint = Endpoint("private", 2001)
        now = [1000]
        cache = RegisterCache(clock=lambda: now[0])
        cache.select_source(endpoint)
        for register, raw in ((2046, 380), (2091, 12345), (2001, 12345)):
            cache.record(endpoint, register, [raw], observed=True)
        now[0] = 1100
        for register, raw in ((2046, 381), (1091, 999), (91102, 33)):
            cache.record(endpoint, register, [raw])
        now[0] = 1200
        values = cache.values(endpoint, connected=True)
        self.assertEqual(set(values), {"2046"})
        self.assertEqual(values["2046"]["value"], 38.1)
        self.assertEqual(values["2046"]["quality"], "fresh")
        self.assertEqual(cache.values(Endpoint("other", 2001), connected=True), {})
        self.assertNotIn("2091", cache.observed_words())
        now[0] = 1500
        self.assertEqual(
            cache.values(endpoint, connected=True)["2046"]["quality"], "stale"
        )

    def test_observer_cannot_merge_data_from_old_endpoint(self):
        cache = RegisterCache()
        cache.select_source(Endpoint("new", 2001))
        cache.observe_frames(
            Endpoint("old", 2001),
            [(99, 16, 2046, 1, b"\x02\x01\x7c", b"", b"", 0, 0, "word-frame")],
        )
        self.assertEqual(cache.observed_words(), {})

    def test_snapshot_does_not_open_or_read_bus(self):
        create = Mock()
        owner = bus.BusConnectionManager(socket_factory=create)
        with (
            patch("backend.routes.lte.warmlink_endpoint", return_value=None),
            patch.object(bus, "manager", owner),
            patch("backend.last_values.store.values", return_value={}),
        ):
            self.assertEqual(lte_snapshot()["values"], {})
        create.assert_not_called()


class PushTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_sends_initial_snapshot_then_only_changes_and_removals(self):
        request = Mock()
        request.is_disconnected = AsyncMock(return_value=False)
        base = {"connection": {}, "metrics": {}, "scan": {}}
        snapshots = [
            {**base, "values": {"2046": {"value": 38}, "2045": {"value": 35}}},
            {**base, "values": {"2046": {"value": 38.1}}},
        ]
        with (
            patch("backend.routes.lte.lte_snapshot", side_effect=snapshots),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            response = await lte_events(request)
            iterator = response.body_iterator
            first = json.loads((await anext(iterator))[6:].strip())
            second = json.loads((await anext(iterator))[6:].strip())
            await iterator.aclose()
        self.assertTrue(first["reset"])
        self.assertFalse(second["reset"])
        self.assertEqual(second["values"], {"2046": {"value": 38.1}})
        self.assertEqual(second["removed"], ["2045"])
        self.assertEqual(response.headers["x-accel-buffering"], "no")
