import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.last_values import LastValues
from backend.parameter_write import encode, write
from backend.cloud_write import WriteConflictError, WriteValidationError
from backend.routes.parameters import blocks, GroupRead, refresh_group
from backend.settings import Endpoint


class SharedValuesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.scope = "same-installation"
        self.path = Path(self.temp.name) / "last.sqlite"
        self.store = LastValues(self.path, lambda: self.scope)

    def row(self, source="cloud", age=0):
        return {
            "value": 36.7,
            "raw": None,
            "unit": "°C",
            "transport": source,
            "timestamp": (
                datetime.now(timezone.utc) - timedelta(seconds=age)
            ).isoformat(),
        }

    def test_newest_transport_wins_and_survives_restart(self):
        older = self.row("cloud", 60)
        newer = self.row("warmlink_raw")
        self.store.remember({"2046": older})
        self.store.remember({"2046": newer})
        self.store.remember({"2046": older})
        restarted = LastValues(self.path, lambda: self.scope)
        value = restarted.values()["2046"]
        self.assertEqual(value["transport"], "warmlink_raw")
        self.assertEqual(value["timestamp"], newer["timestamp"])
        self.assertEqual(value["quality"], "cached")

    def test_old_value_stays_stale_and_other_installation_is_isolated(self):
        self.store.remember({"2046": self.row(age=3600)})
        self.assertEqual(self.store.values()["2046"]["quality"], "stale")
        self.scope = "different-device"
        self.assertEqual(self.store.values(), {})

    def test_newer_bus_value_replaces_old_cloud_cache_without_claiming_online(self):
        from backend.last_values import fill_dashboard

        old = {**self.row("cloud", 3600), "quality": "stale"}
        new = {**self.row("warmlink_raw"), "quality": "cached"}
        snapshot = {"status": "unavailable", "metrics": {"supply": old}}
        with patch("backend.last_values.store.values", return_value={"2046": new}):
            result = fill_dashboard(snapshot)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["metrics"]["supply"]["transport"], "warmlink_raw")
        self.assertEqual(result["metrics"]["supply"]["timestamp"], new["timestamp"])

    def test_nonfinite_value_does_not_break_telemetry(self):
        self.store.remember({"2046": {**self.row(), "value": float("nan")}})
        self.assertEqual(self.store.values(), {})


class ParameterWriteTests(unittest.TestCase):
    @contextmanager
    def bus(self, client):
        yield client

    def test_signed_temperature_and_enum_encoding(self):
        self.assertEqual(encode("-1,5", {"type": "TEMP1"}), 65521)
        self.assertEqual(encode("12:35", {"type": "TIME_HHMM"}), 3107)
        for value in ("nan", "inf", "0.01", "3276.8"):
            with self.assertRaises(WriteValidationError):
                encode(value, {"type": "TEMP1"})
        with self.assertRaises(WriteValidationError):
            encode("2", {"type": "ENUM", "value_map": {"0": "Aus", "1": "Ein"}})

    def test_cross_transport_baseline_conversion_preserves_scale_enums_and_timers(self):
        from backend.parameter_write import convert_baseline

        self.assertEqual(
            convert_baseline(1105, {"type": "TEMP1"}, "12.5", "cloud", "warmlink_raw"),
            "125",
        )
        self.assertEqual(
            convert_baseline(1105, {"type": "TEMP1"}, "65521", "warmlink_raw", "cloud"),
            "-1.5",
        )
        self.assertEqual(
            convert_baseline(
                1011,
                {"type": "DIGI1", "value_map": {"0": "Aus", "1": "Ein"}},
                "1",
                "warmlink_raw",
                "cloud",
            ),
            "1",
        )
        self.assertEqual(
            convert_baseline(
                1268,
                {"type": "TIMER_BITPAIR"},
                "0000000010000001",
                "cloud",
                "warmlink_raw",
            ),
            "129",
        )
        self.assertEqual(
            convert_baseline(
                1268, {"type": "TIMER_BITPAIR"}, "129", "warmlink_raw", "cloud"
            ),
            "0000000010000001",
        )

    def test_read_only_register_cannot_be_written(self):
        with self.assertRaises(WriteValidationError):
            write(2046, "warmlink_raw", "40", "367")

    def run_write(self, client, expected="10"):
        endpoint = Endpoint("192.168.1.50", 2001, timeout=5)
        with (
            patch("backend.settings.warmlink_endpoint", return_value=endpoint),
            patch(
                "backend.warmlink.open_warmlink", side_effect=lambda _: self.bus(client)
            ),
            patch("backend.parameter_write._last_write", {}),
            patch("backend.parameter_write.time.sleep"),
            patch("backend.last_values.remember_words"),
        ):
            return write(1105, "warmlink_raw", "2.5", expected)

    def test_generic_parameter_writes_once_in_engineering_units_with_readback(self):
        client = Mock()
        client.read_holding.side_effect = [[10], [25]]
        result = self.run_write(client)
        self.assertTrue(result["confirmed"])
        client.write_one.assert_called_once_with(1105, 25)

    def test_curve_point_checks_current_target_limits_before_any_write(self):
        endpoint = Endpoint("192.168.1.50", 2001, timeout=5)
        client = Mock()
        client.read_holding.side_effect = [[400], [200, 550]]
        with (
            patch("backend.settings.warmlink_endpoint", return_value=endpoint),
            patch(
                "backend.warmlink.open_warmlink", side_effect=lambda _: self.bus(client)
            ),
            patch("backend.parameter_write._last_write", {}),
        ):
            with self.assertRaisesRegex(WriteValidationError, "R10/R11"):
                write(1250, "warmlink_raw", "60", "400")
        client.write_one.assert_not_called()

    def test_graph_write_cannot_change_linear_offset_after_curve_mode_switch(self):
        endpoint = Endpoint("192.168.1.50", 2001, timeout=5)
        client = Mock()
        client.read_holding.side_effect = [[350], [1]]
        with (
            patch("backend.settings.warmlink_endpoint", return_value=endpoint),
            patch("backend.warmlink.open_warmlink", side_effect=lambda _: self.bus(client)),
            patch("backend.parameter_write._last_write", {}),
        ):
            with self.assertRaisesRegex(WriteConflictError, "Sieben-Punkt-Kurve"):
                write(1235, "warmlink_raw", "40", "350", curve_edit=True)
        client.write_one.assert_not_called()

    def test_virtual_sg_input_is_not_forwarded_to_lte(self):
        with patch("backend.warmlink.open_warmlink") as connection:
            with self.assertRaisesRegex(
                WriteValidationError, "direkten Standard-Modbus"
            ):
                write(8801, "warmlink_raw", "2", "1")
        connection.assert_not_called()

    def test_changed_baseline_never_writes(self):
        client = Mock()
        client.read_holding.return_value = [11]
        with self.assertRaises(WriteConflictError):
            self.run_write(client)
        client.write_one.assert_not_called()

    def test_uncertain_write_is_not_replayed(self):
        client = Mock()
        client.read_holding.return_value = [10]
        client.write_one.side_effect = TimeoutError()
        self.assertFalse(self.run_write(client)["confirmed"])
        client.write_one.assert_called_once()

    def test_timer_parameter_uses_complete_program_barriers(self):
        current = {str(reg): 0 for reg in range(1244, 1250)}
        with (
            patch("backend.timers.read", return_value={"values": current}),
            patch("backend.timers.write", return_value={"confirmed": True}) as writer,
        ):
            write(1245, "warmlink_raw", "7", "0")
        args = writer.call_args.args
        self.assertEqual(args[:2], ("silent", "warmlink_raw"))
        self.assertEqual(args[2]["1245"], 7)
        self.assertEqual(args[3], current)

    def test_source_granted_cloud_parameter_uses_reviewed_control_endpoint(self):
        from backend import cloud_write

        reader = Mock(token="test-token", device_code="test-device")
        reader.read_codes.side_effect = [
            {"D01": {"value": "1"}},
            {"D01": {"value": "2.5"}},
        ]
        reader._ok.return_value = True
        grant = {
            "code": "D01",
            "register": 1105,
            "write_allowed": True,
            "write_code": "D01",
            "write_values": {},
        }
        with (
            patch("backend.cloud_state.catalog", return_value=[grant]),
            patch(
                "backend.cloud_write.credentials",
                return_value=("user", "password", "device"),
            ),
            patch("backend.cloud_write._reader", return_value=reader),
            patch.object(cloud_write, "_LAST_WRITE", 0),
            patch("backend.cloud_write.merge"),
            patch("backend.cloud_write.time.sleep"),
        ):
            self.assertTrue(write(1105, "cloud", "2.5", "1")["confirmed"])
        reader._post.assert_called_once()
        self.assertEqual(reader._post.call_args.args[1]["param"][0]["value"], "2.5")


class GroupReadTests(unittest.TestCase):
    def test_fc03_combines_adjacent_words_up_to_90(self):
        self.assertEqual(
            blocks(list(range(1011, 1105)) + [1158]), [(1011, 90), (1101, 4), (1158, 1)]
        )

    def test_fresh_group_does_not_open_bus(self):
        row = {
            "value": 1,
            "transport": "warmlink_raw",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with (
            patch("backend.routes.parameters.store.values", return_value={"1105": row}),
            patch("backend.warmlink.open_warmlink") as bus,
        ):
            result = refresh_group(
                GroupRead(transport="warmlink_raw", registers=[1105]),
                Mock(headers={"x-foxair-admin": "1"}),
            )
        self.assertEqual(result["status"], "current")
        bus.assert_not_called()


if __name__ == "__main__":
    unittest.main()
