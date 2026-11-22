from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from backend import cloud_config, local_history
from backend.register_definitions import STANDARD_DASHBOARD_BLOCKS
from backend.routes import overview


class LocalOverviewTests(TestCase):
    def test_profiles_share_storage_and_plan_only_missing_adjacent_registers(self):
        with (
            TemporaryDirectory() as folder,
            patch.object(cloud_config, "STATE_DIR", Path(folder)),
        ):
            self.assertEqual(
                overview.settings()["mobile"][:3], ["return", "supply", "spread"]
            )
            profiles = {
                "desktop": ["fan_one", "evi_in", "fan_two", "evaporator"],
                "mobile": ["compressor_starts", "evaporator"],
            }
            cloud_config._atomic_json(overview.config_path(), profiles)
            self.assertEqual(
                overview.settings(),
                {**profiles, "mobile_columns": 3, "desktop_columns": 8},
            )
            blocks = overview.standard_ranges(STANDARD_DASHBOARD_BLOCKS)
            self.assertEqual(
                blocks[len(STANDARD_DASHBOARD_BLOCKS) :],
                ((2023, 1), (2063, 1), (2074, 2)),
            )

    def test_history_buffers_deduplicates_flushes_and_expires(self):
        with (
            TemporaryDirectory() as folder,
            patch.object(cloud_config, "STATE_DIR", Path(folder)),
            patch.object(local_history, "PENDING", {}),
            patch.object(local_history, "SEEN", set()),
            patch("backend.last_values.installation_key", return_value="unit-test"),
            patch("backend.local_history.time.time", return_value=600) as clock,
        ):
            cloud_config._atomic_json(
                local_history.config_path(), {"enabled": True, "retention_days": 1}
            )

            def record(stamp, value):
                local_history.record(
                    {
                        "2046": {
                            "timestamp": datetime.fromtimestamp(
                                stamp, timezone.utc
                            ).isoformat(),
                            "value": value,
                            "transport": "standard_modbus",
                        }
                    },
                    "unit-test",
                )

            record(560, 30)
            record(560, 30)
            record(590, "34,0")
            self.assertFalse((Path(folder) / "local-history.sqlite").exists())
            local_history.flush()
            points = local_history.series(2046, 1)["points"]
            self.assertEqual(
                [(point["value"], point["min"], point["max"]) for point in points],
                [(32, 30, 34)],
            )
            self.assertEqual(points[0]["source"], "standard_modbus")
            self.assertEqual(local_history.PENDING, {})

            clock.return_value = 90000
            local_history.flush()
            with closing(local_history.connect()) as db:
                self.assertEqual(
                    db.execute("SELECT count(*) FROM history").fetchone()[0], 0
                )
