from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import cloud_config
from backend.main import app
from backend.server import TCPPeerApp


class LanAccessTests(TestCase):
    def test_admin_can_add_and_remove_names_from_the_lan_ip(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(cloud_config, "STATE_DIR", root),
                patch.object(cloud_config, "ADMIN_FILE", root / "admin.json"),
                patch.dict(
                    "os.environ",
                    {
                        "FOXAIR_CONTAINER": "1",
                        "FOXAIR_LAN_HTTP": "1",
                        "FOXAIR_LAN_HOSTS": "fixed.home.arpa",
                        "FOXAIR_TRUSTED_PROXY_IPS": "",
                    },
                ),
                patch.object(
                    cloud_config, "is_admin_session", return_value=False
                ) as admin,
            ):
                cloud_config._atomic_json(
                    cloud_config.ADMIN_FILE, {"setup_lan_hostname": "first.home.arpa"}
                )
                client = TestClient(
                    TCPPeerApp(app),
                    base_url="http://192.0.2.1",  # Default Host is set explicitly below.
                    client=("192.168.150.25", 50000),
                    headers={"Host": "192.168.10.10:18081", "X-FoxAir-Admin": "1"},
                )
                health = "/api/health"
                save = "/api/admin/lan-access/save"
                alias = {"Host": "new.home.arpa:18081"}
                self.assertEqual(client.get(health, headers=alias).status_code, 403)
                login = client.post(
                    "/api/admin/login",
                    json={"admin_password": "test-password"},
                    headers={
                        "Origin": "https://192.168.10.10:18081",
                        "X-Forwarded-Proto": "https",
                    },
                )
                self.assertEqual(login.status_code, 403)
                self.assertIn("Dein Browser verwendet HTTPS", login.json()["detail"])
                self.assertEqual(
                    client.post(save, json={"hosts": ["new.home.arpa"]}).status_code,
                    403,
                )

                admin.return_value = True
                for bad_name in (
                    "*.home.arpa",
                    "https://new.home.arpa",
                    "new.home.arpa:443",
                ):
                    self.assertEqual(
                        client.post(save, json={"hosts": [bad_name]}).status_code, 422
                    )
                self.assertEqual(
                    client.post(
                        save,
                        json={"hosts": ["new.home.arpa"]},
                        headers={"Origin": "http://other.home.arpa"},
                    ).status_code,
                    403,
                )
                response = client.post(
                    save, json={"hosts": ["NEW.Home.Arpa.", "new.home.arpa"]}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["hosts"], ["new.home.arpa"])
                self.assertEqual(client.get(health, headers=alias).status_code, 200)

                self.assertEqual(
                    client.post(
                        save, json={"hosts": [], "proxy_ips": ["192.168.150.0/24"]}
                    ).status_code,
                    422,
                )
                self.assertEqual(
                    client.post(
                        save,
                        json={
                            "hosts": ["new.home.arpa"],
                            "proxy_ips": ["192.168.150.25"],
                        },
                    ).status_code,
                    200,
                )
                forwarded = {
                    **alias,
                    "Origin": "https://new.home.arpa:18081",
                    "X-Forwarded-Proto": "https",
                }
                self.assertEqual(
                    client.post(
                        save, json={"hosts": ["new.home.arpa"]}, headers=forwarded
                    ).json()["proxy_ips"],
                    ["192.168.150.25"],
                )
                forged = {
                    **forwarded,
                    "Origin": "https://other.home.arpa",
                    "X-Forwarded-Host": "other.home.arpa",
                }
                self.assertEqual(
                    client.post(save, json={"hosts": []}, headers=forged).status_code,
                    403,
                )
                other_peer = TestClient(
                    TCPPeerApp(app), client=("192.168.150.26", 50000)
                )
                self.assertEqual(
                    other_peer.post(
                        save,
                        json={"hosts": []},
                        headers={**forwarded, "X-FoxAir-Admin": "1"},
                    ).status_code,
                    403,
                )
                external = TestClient(TCPPeerApp(app), client=("203.0.113.25", 50000))
                self.assertEqual(external.get(health, headers=alias).status_code, 403)

                self.assertEqual(client.post(save, json={"hosts": []}).status_code, 200)
                self.assertEqual(client.get(health, headers=alias).status_code, 403)
                for fixed in ("fixed.home.arpa", "first.home.arpa", "192.168.10.10"):
                    self.assertEqual(
                        client.get(health, headers={"Host": fixed}).status_code, 200
                    )
