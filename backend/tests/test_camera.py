from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import camera


class CameraTests(TestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(camera.cloud_config, "STATE_DIR", Path(root)))
        self.enterContext(patch.object(camera, "paused", return_value=False))
        app = FastAPI()
        app.include_router(camera.router)
        self.client = TestClient(app)
        self.settings = {"enabled": True, "url": "http://camera.local/live.mjpg"}
        camera.cloud_config._atomic_json(camera.settings_path(), self.settings)

    def test_guest_cannot_see_url_or_open_stream(self):
        self.assertEqual(self.client.get("/api/camera/settings").json()["url"], "")
        with patch.object(camera, "open_camera") as open_camera:
            self.assertEqual(self.client.get("/api/camera/stream").status_code, 403)
            open_camera.assert_not_called()

    def test_stream_forwards_mjpeg_and_releases_both_handles(self):
        connection, upstream = Mock(), Mock()
        upstream.read1.side_effect = [
            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n",
            b"",
        ]
        media = 'multipart/x-mixed-replace; boundary="frame"'
        with (
            patch.object(camera, "principal", return_value={"role": "viewer"}),
            patch.object(
                camera, "open_camera", return_value=(connection, upstream, media)
            ),
        ):
            result = self.client.get(
                "/api/camera/stream", headers={"sec-fetch-dest": "image"}
            )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["content-type"], media)
        self.assertEqual(result.headers["x-accel-buffering"], "no")
        self.assertIn(b"Content-Type: image/jpeg", result.content)
        upstream.close.assert_called_once()
        connection.close.assert_called_once()

    def test_resolved_loopback_is_rejected_before_connecting(self):
        address = (2, 1, 6, "", ("127.0.0.1", 80))
        with (
            patch.object(camera.socket, "getaddrinfo", return_value=[address]),
            patch.object(camera.socket, "create_connection") as connect,
        ):
            with self.assertRaises(camera.HTTPException) as error:
                camera.open_camera(camera.endpoint(self.settings["url"]))
            self.assertEqual(error.exception.status_code, 422)
            connect.assert_not_called()

    def test_jpeg_mode_returns_a_single_uncached_image_and_closes_the_camera(self):
        camera.cloud_config._atomic_json(
            camera.settings_path(),
            {**self.settings, "mode": "jpeg", "interval_ms": 1500},
        )
        connection, upstream = Mock(), Mock()
        upstream.read.return_value = b"\xff\xd8test\xff\xd9"
        with (
            patch.object(camera, "principal", return_value={"role": "viewer"}),
            patch.object(
                camera, "open_camera", return_value=(connection, upstream, "image/jpeg")
            ) as open_camera,
        ):
            result = self.client.get("/api/camera/stream?frame=1")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.content, upstream.read.return_value)
        self.assertEqual(result.headers["cache-control"], "no-store")
        self.assertEqual(open_camera.call_args.args[1], "jpeg")
        upstream.close.assert_called_once()
        connection.close.assert_called_once()
