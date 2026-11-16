from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from backend import device_name
from backend.cloud_read import project_dashboard


class DashboardIdentityTests(unittest.TestCase):
    def test_name_persists_and_is_not_reused_for_another_device(self):
        account = ("user", "password", "selected")
        with TemporaryDirectory() as directory, \
                patch.object(device_name, "NAME_FILE", Path(directory) / "name.json"), \
                patch("backend.device_name.credentials", return_value=account) as credentials:
            self.assertEqual(device_name.get_name(), "FoxAir")
            device_name.remember_name({"deviceNickName": "Mein Fox", "deviceName": "Model"}, account)
            self.assertEqual(device_name.get_name(), "Mein Fox")
            credentials.return_value = ("user", "password", "other")
            self.assertEqual(device_name.get_name(), "FoxAir")

    def test_actual_frequency_uses_t31_and_preserves_stale_quality(self):
        values = {"T30": {"value": 70}, "T31": {"value": 43}}
        self.assertEqual(project_dashboard(values)["compressor_frequency"]["value"], 43)
        self.assertEqual(project_dashboard(values, stale=True)["compressor_frequency"]["quality"], "stale")

    def test_decimal_cloud_switches_use_same_labels_as_local_bus(self):
        values = {"Power":{"value":"1.0"},"H22":{"value":"0.0"}}
        self.assertEqual(project_dashboard(values)["power"]["value"], "Ein")
        self.assertEqual(project_dashboard(values)["silent"]["value"], "Silent-Modus aus")
