from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from backend import cloud_config, local_history
from backend.register_definitions import STANDARD_DASHBOARD_BLOCKS
from backend.routes import overview
from fastapi import FastAPI
from fastapi.testclient import TestClient
from scripts.repair_local_history import repair


class LocalOverviewTests(TestCase):
    def test_csv_exports_measurements_and_defrost_in_the_requested_window(self):
        app = FastAPI()
        app.include_router(local_history.router)
        url = "/api/history/local/export"
        dates = {"start": "1970-01-01T00:05:00Z", "end": "1970-01-01T00:10:00Z"}
        with (
            TemporaryDirectory() as folder,
            patch.object(cloud_config, "STATE_DIR", Path(folder)),
        ):
            with closing(local_history.connect()) as db, db:
                db.executemany(
                    "INSERT INTO history VALUES (?,?,?,?,?,?,?,?)",
                    [
                        ("local", 2046, 300, "warmlink_raw", 2, 63, 30, 33),
                        ("local", 2046, 600, "warmlink_raw", 1, 40, 40, 40),
                    ],
                )
                db.execute(
                    "INSERT INTO defrost VALUES (?,?,?,?)",
                    ("local", "warmlink_raw", 400, 470),
                )
            client = TestClient(app, base_url="https://testserver")
            self.assertEqual(client.get(url, params=dates).status_code, 403)
            with patch.object(cloud_config, "require_admin"):
                reply = client.get(url, params=dates)
            self.assertEqual(reply.status_code, 200)
            self.assertIn("foxair-verlauf.csv", reply.headers["Content-Disposition"])
            self.assertIn(";31.5;30.0;33.0;2;", reply.text)
            self.assertIn("Abtauvorgang;", reply.text)
            self.assertIn(";70", reply.text)
            self.assertNotIn("T00:10:00", reply.text)

    def test_repair_backs_up_before_restoring_orphaned_archive(self):
        with (
            TemporaryDirectory() as folder,
            patch.object(cloud_config, "STATE_DIR", Path(folder)),
        ):
            path = Path(folder) / "local-history.sqlite"
            with closing(local_history.connect()) as db, db:
                db.execute(
                    "INSERT INTO history VALUES (?,?,?,?,?,?,?,?)",
                    ("old", 2046, 300, "warmlink_raw", 1, 34, 34, 34),
                )
                self.assertEqual(local_history.archive_scopes(db), ("local", "old"))

            repair(path, "current")
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(
                    db.execute("SELECT scope FROM history").fetchone(), ("current",)
                )
            backups = list(Path(folder).glob("local-history.backup-*.sqlite"))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as db:
                self.assertEqual(
                    db.execute("SELECT scope FROM history").fetchone(), ("old",)
                )

    def test_defrost_records_only_complete_observed_cycles(self):
        with (
            TemporaryDirectory() as folder,
            patch.object(cloud_config, "STATE_DIR", Path(folder)),
            patch.object(local_history, "DEFROST_STATE", {}),
            patch.object(local_history, "DEFROST_EVENTS", {}),
            patch.object(local_history, "PENDING", {}),
            patch.object(local_history, "SEEN", set()),
            patch("backend.local_history.time.time") as clock,
        ):
            cloud_config._atomic_json(local_history.config_path(), {"enabled": True})

            def state(stamp, raw):
                clock.return_value = stamp
                local_history.record(
                    {
                        "2012": {
                            "timestamp": datetime.fromtimestamp(
                                stamp, timezone.utc
                            ).isoformat(),
                            "raw": raw,
                            "value": raw,
                            "transport": "display_modbus",
                        }
                    },
                )

            state(400, 2)  # Already in progress when the first status arrives.
            state(440, 1)
            state(480, 2)
            state(530, 2)
            state(550, 1)
            state(580, 2)
            state(900, 1)  # A gap leaves this duration unknown.
            local_history.flush()
            self.assertEqual(
                local_history.defrost_events(1)["events"],
                [
                    {
                        "start": datetime.fromtimestamp(480, timezone.utc).isoformat(),
                        "duration_seconds": 70,
                    }
                ],
            )
            self.assertEqual(local_history.latest_defrost(), {
                "finished_at": datetime.fromtimestamp(550, timezone.utc).isoformat(),
            })

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
                {
                    **profiles,
                    "mobile_columns": 3,
                    "desktop_columns": 8,
                    "mobile_glance": overview.GLANCE_DEFAULT,
                    "desktop_glance": overview.GLANCE_DEFAULT,
                },
            )
            blocks = overview.standard_ranges(STANDARD_DASHBOARD_BLOCKS)
            self.assertEqual(
                blocks[len(STANDARD_DASHBOARD_BLOCKS) :],
                ((2023, 1), (2063, 1), (2074, 2)),
            )

    def test_overview_accepts_more_than_previous_tile_limits(self):
        fields = sorted(overview.OPTIONS)
        self.assertGreater(len(fields), 18)
        app = FastAPI()
        app.include_router(overview.router)
        with (
            TemporaryDirectory() as folder,
            patch.object(cloud_config, "STATE_DIR", Path(folder)),
            patch.object(cloud_config, "require_admin"),
        ):
            client = TestClient(app)
            profiles = {name: fields for name in ("mobile", "desktop", "mobile_glance", "desktop_glance")}
            result = client.post("/api/overview", json=profiles)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(client.get("/api/overview").json(), {
                **profiles, "mobile_columns": 3, "desktop_columns": 8,
            })

    def test_pump_feedback_is_available_in_both_dashboard_areas(self):
        with (
            TemporaryDirectory() as folder,
            patch.object(cloud_config, "STATE_DIR", Path(folder)),
        ):
            from backend.register_definitions import LTE_DASHBOARD_BLOCKS

            profiles = {
                **overview.settings(),
                "desktop": ["pump_feedback"],
                "mobile_glance": ["pump_feedback"],
            }
            overview.validate_profiles(profiles)
            cloud_config._atomic_json(overview.config_path(), profiles)
            self.assertIn((2116, 1), overview.standard_ranges(STANDARD_DASHBOARD_BLOCKS))
            self.assertIn((2115, 2), LTE_DASHBOARD_BLOCKS)

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
