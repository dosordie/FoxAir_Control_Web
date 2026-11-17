from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import Mock, patch

from backend import bus_connection as bus, cloud_insights as cloud
from backend.settings import Endpoint
from backend.cloud_read import CloudError
from backend.cloud_read import CloudReader


class ConnectionTests(unittest.TestCase):
    def test_passive_projection_keeps_age_source_and_selected_target(self):
        from backend.register_cache import RegisterCache

        endpoint = Endpoint("private", 2001)
        now = [1000]
        cache = RegisterCache(clock=lambda: now[0])
        cache.select_source(endpoint)
        for register, raw in ((2046, 380), (1158, 350), (2014, 365)):
            cache.record(endpoint, register, [raw], observed=True)
        now[0] = 1100
        values = cache.metrics(
            {"supply": 2046, "target": 1158}, endpoint, connected=True
        )
        self.assertEqual(values["supply"]["value"], 38)
        self.assertEqual(values["target"]["value"], 36.5)
        self.assertEqual(values["target"]["source_code"], "2014")
        self.assertEqual(values["supply"]["quality"], "observed")
        timestamp = values["supply"]["timestamp"]
        now[0] = 1400
        old = cache.metrics({"supply": 2046}, endpoint, connected=True)["supply"]
        self.assertEqual(old["quality"], "stale")
        self.assertEqual(old["timestamp"], timestamp)
        self.assertEqual(
            cache.metrics({"supply": 2046}, Endpoint("other", 2001), connected=True), {}
        )

    def test_passive_dashboard_never_opens_a_socket_or_reads_bus(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        with (
            patch("backend.main.open_warmlink") as active,
            patch.object(bus, "observed_metrics", return_value={}),
        ):
            response = TestClient(app).get(
                "/api/dashboard?transport=warmlink_raw&passive=true"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unavailable")
        active.assert_not_called()

    def test_browser_lease_expires_and_permanent_does_not_depend_on_it(self):
        owner = bus.BusConnectionManager()
        with (
            patch.object(owner, "start"),
            patch("backend.bus_connection.time.monotonic", return_value=0),
        ):
            owner.lease()
        self.assertTrue(owner.wanted("browser", 89))
        self.assertFalse(owner.wanted("browser", 90))
        self.assertTrue(owner.wanted("permanent", 10000))
        self.assertFalse(owner.wanted("on_demand", 89))

    def test_operations_reuse_one_socket_and_discard_poisoned_session(self):
        endpoint = Endpoint("private", 2001)
        create = Mock()
        owner = bus.BusConnectionManager(socket_factory=create)
        with owner.operation(endpoint) as first:
            pass
        with owner.operation(endpoint) as second:
            self.assertIs(first, second)
        create.assert_called_once()
        with owner.operation(endpoint) as second:
            second.poisoned = True
        self.assertFalse(owner.connected)
        create.return_value.close.assert_called_once()
        self.assertTrue(owner.stop())

    def test_observed_block_is_distinct_from_write_intent(self):
        from backend.register_cache import RegisterCache

        endpoint = Endpoint("private", 2001)
        cache = RegisterCache()
        cache.select_source(endpoint)
        frame = (99, 16, 2045, 2, b"\x04\x00\x01\x00\x02", b"", b"", 0, 0, "word-frame")
        cache.observe_frames(endpoint, [frame])
        self.assertEqual(cache.observed_words()["2046"]["raw"], 2)
        self.assertEqual(cache.observed_words()["2046"]["quality"], "observed")
        cache.observe_frames(endpoint, [(*frame[:2], 2047, *frame[3:9], "short-write")])
        self.assertNotIn("2047", cache.observed_words())


class CloudInsightTests(unittest.TestCase):
    def setUp(self):
        self.reader = Mock()
        self.reader.device_code = "private-device"
        self.reader._ok.return_value = True
        self.patches = [
            patch.object(cloud, "_cache", {}),
            patch.object(cloud, "_attempts", {}),
            patch.object(cloud, "_details", {}),
            patch(
                "backend.cloud_insights.credentials",
                return_value=("user", "secret", "private-device"),
            ),
            patch("backend.cloud_insights._reader", return_value=self.reader),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def test_service_protocol_follows_verified_device_and_product(self):
        client = CloudReader("user", "secret", "selected")
        client._service_devices = {
            "selected": {"deviceId": "internal-device", "productId": "internal-product"}
        }

        def reply(obj):
            return {"isReusltSuc": True, "objectResult": obj}

        with (
            patch.object(client, "devices"),
            patch.object(
                client,
                "_request_auth",
                side_effect=[
                    reply({"deviceCode": "selected", "productId": "internal-product"}),
                    reply(
                        {
                            "productId": "internal-product",
                            "protocalId": "internal-protocol",
                        }
                    ),
                ],
            ) as calls,
        ):
            self.assertEqual(client.service_protocol(), "internal-protocol")
            self.assertEqual(
                calls.call_args_list[0].args,
                ("app/device/queryDeviceById", {"deviceId": "internal-device"}),
            )
            self.assertEqual(
                calls.call_args_list[1].args,
                ("app/product/queryProductById", {"id": "internal-product"}),
            )
        with (
            patch.object(client, "devices"),
            patch.object(
                client,
                "_request_auth",
                return_value=reply(
                    {"deviceCode": "wrong", "productId": "internal-product"}
                ),
            ) as calls,
        ):
            with self.assertRaises(CloudError):
                client.service_protocol()
            self.assertEqual(calls.call_count, 1)

    def test_history_window_alias_and_timezone_validation(self):
        cloud.history_args(
            "2078+9", "2026-11-01 00:00:00", "2026-11-16 00:00:00", "month", 1
        )
        for address, start, end, zone in [
            ("9999", "2026-11-01 00:00:00", "2026-11-16 00:00:00", 1),
            ("2045", "bad", "bad", 1),
            ("2045", "2026-01-01 00:00:00", "2026-11-16 00:00:00", 1),
            ("2045", "2026-11-01 00:00:00", "2026-11-16 00:00:00", 2),
        ]:
            with self.assertRaises(ValueError):
                cloud.history_args(address, start, end, "day", zone)

    def test_empty_ota_is_successful_no_update_and_cached(self):
        self.reader._request_auth.return_value = {"objectResult": []}
        result = cloud.request("ota")
        self.assertFalse(result["available"])
        self.assertTrue(cloud.request("ota")["cached"])
        self.reader._request_auth.assert_called_once()

    def test_failed_requests_are_rate_limited_too(self):
        self.reader._request_auth.side_effect = CloudError("Cloud-Fehler")
        with self.assertRaises(CloudError):
            cloud.request("ota")
        with self.assertRaises(ValueError):
            cloud.request("ota")
        self.reader._request_auth.assert_called_once()

    def test_current_day_zero_is_not_claimed_as_complete_consumption(self):
        today = datetime.now(timezone(timedelta(hours=1))).strftime("%Y-%m-%d")
        self.reader._request_auth.return_value = {
            "objectResult": {
                "valueList": [
                    {"dateTime": today + " 00:00:00", "addressValue": "0.000"},
                    {"dateTime": "bad", "addressValue": "NaN"},
                ]
            }
        }
        result = cloud.request("history", {"address": "2078+9"})
        self.assertEqual(len(result["points"]), 1)
        self.assertTrue(result["points"][0]["incomplete"])

    def test_hour_only_history_labels_become_browser_parseable_timestamps(self):
        self.reader._request_auth.return_value = {
            "objectResult": {
                "valueList": [{"dateTime": "2026-11-16 23", "addressValue": "35.1"}]
            }
        }
        result = cloud.request("history", {"address": "2046"})
        self.assertEqual(result["points"][0]["time"], "2026-11-16T23:00:00+01:00")

    def test_history_missing_points_stay_missing_and_empty_is_valid(self):
        self.reader._request_auth.return_value = {
            "objectResult": {
                "valueList": [
                    {"dateTime": "2026-11-16 02", "addressValue": "35.1"},
                    {"dateTime": "2026-11-16 03"},
                    {"dateTime": "2026-11-16 04", "addressValue": "NaN"},
                ]
            }
        }
        self.assertEqual(
            len(cloud.request("history", {"address": "2046"})["points"]), 1
        )
        self.reader._request_auth.return_value = {"objectResult": {"valueList": []}}
        with patch.object(
            cloud.time, "monotonic", return_value=cloud.time.monotonic() + 11
        ):
            self.assertEqual(
                cloud.request("history", {"address": "2045"})["points"], []
            )

    def test_metadata_does_not_expose_identifiers_or_create_grants(self):
        self.reader._request_auth.return_value = {
            "objectResult": {
                "total": 1,
                "dataList": [
                    {
                        "address": "2157",
                        "content": "PV_Power",
                        "deviceCode": "private",
                        "token": "secret",
                        "write_allowed": True,
                    }
                ],
            }
        }
        result = cloud.request("metadata")
        self.assertEqual(
            result["items"],
            [
                {
                    "address": "2157",
                    "content": "PV_Power",
                    "comparison": "Keine bestätigte Cloud-Zuordnung – nur Herstellerangabe",
                }
            ],
        )
        body = self.reader._request_auth.call_args.args[1]
        self.assertEqual(
            (body["pageIndex"], body["pageSize"], body["paramName"], body["num"]),
            (1, 9999, "", ""),
        )
        self.reader.service_protocol.assert_called_once()

    def test_enum_references_are_account_bound_and_strip_provider_ids(self):
        self.reader._request_auth.return_value = {
            "objectResult": {
                "dataList": [{"address": "1046", "detailId": "private-detail"}]
            }
        }
        result = cloud.request("metadata")
        key = result["items"][0]["enum_key"]
        self.assertNotIn("private-detail", str(result))
        self.reader._request_auth.return_value = {
            "objectResult": [
                {
                    "value": "0",
                    "enMeaning": "Off",
                    "detailId": "private-detail",
                    "creator": "private",
                }
            ]
        }
        result = cloud.request("enum", {"key": key})
        self.assertEqual(result["items"], [{"value": "0", "enMeaning": "Off"}])
        self.assertEqual(
            self.reader._request_auth.call_args.args[1], {"detailId": "private-detail"}
        )
        with patch(
            "backend.cloud_insights.credentials",
            return_value=("other", "secret", "other-device"),
        ):
            with self.assertRaises(ValueError):
                cloud.request("enum", {"key": key})

    def test_ai_support_does_not_imply_enabled_and_only_flags_are_exposed(self):
        self.reader._request_auth.return_value = {
            "objectResult": {
                "supportAIFreqState": 1,
                "enAIPower": 0,
                "supportSGReadyState": 1,
                "setSGReadyMode": 0,
                "deviceCode": "private",
                "totalElecBillYear": 999,
            }
        }
        result = cloud.request("ai")
        self.assertTrue(result["frequency_supported"])
        self.assertFalse(result["ai_enabled"])
        self.assertTrue(result["sg_supported"])
        self.assertEqual(result["sg_mode"], 0)
        self.assertNotIn("private", str(result))
        self.assertNotIn("totalElecBillYear", result)

    def test_unknown_extra_schemas_fail_without_dumping_response(self):
        self.reader._request_auth.return_value = {"objectResult": {"secret": "private"}}
        for kind in ("ota", "history", "metadata"):
            with self.assertRaises(CloudError) as caught:
                cloud.request(kind, {"address": "2046"} if kind == "history" else {})
            self.assertNotIn("private", str(caught.exception))
