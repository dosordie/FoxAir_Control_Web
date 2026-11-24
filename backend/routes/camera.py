from email.message import Message
from http.client import HTTPConnection, HTTPSConnection, HTTPException as UpstreamError
from ipaddress import ip_address, ip_network
import re
import socket
from threading import BoundedSemaphore
from urllib.parse import urlsplit
from typing import Literal

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from backend import cloud_config
from backend.transport_selection import paused
from backend.users import principal

router = APIRouter(prefix="/api/camera")
LAN_NETWORKS = tuple(
    ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)
STREAM_SLOTS = BoundedSemaphore(4)
TIMEOUT = 5
MAX_JPEG_BYTES = 8 * 1024 * 1024
IMAGE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox; default-src 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class CameraStream(StreamingResponse):
    def __init__(self, *args, release, **kwargs):
        super().__init__(*args, **kwargs)
        self.release = release

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.release()


class CameraSettings(BaseModel):
    enabled: bool = False
    url: str = Field(default="", max_length=2048)
    mode: Literal["jpeg", "mjpeg"] = "mjpeg"
    interval_ms: int = Field(default=2000, ge=200, le=60000)


def settings_path():
    return cloud_config.STATE_DIR / "camera.json"


def camera_settings():
    return CameraSettings(**cloud_config._read_json(settings_path()))


def endpoint(url):
    try:
        if (
            any(ord(character) < 33 or ord(character) > 126 for character in url)
            or "\\" in url
        ):
            raise ValueError
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or (parts.port is not None and parts.port < 1)
        ):
            raise ValueError
        return parts
    except ValueError:
        raise HTTPException(
            422, "Bitte eine gültige HTTP- oder HTTPS-URL ohne Zugangsdaten eingeben."
        ) from None


@router.get("/settings")
def get_settings(request: Request):
    config = camera_settings()
    return {
        **config.model_dump(),
        "url": config.url if cloud_config.is_admin_session(request) else "",
    }


@router.post("/settings")
def save_settings(payload: CameraSettings, request: Request):
    cloud_config.require_admin(request)
    payload.url = payload.url.strip()
    if payload.enabled or payload.url:
        endpoint(payload.url)
    cloud_config._atomic_json(settings_path(), payload.model_dump())
    return payload


def open_camera(parts, mode="mjpeg"):
    secure = parts.scheme == "https"
    port = parts.port or (443 if secure else 80)
    addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    allowed = [
        entry[4][0]
        for entry in addresses
        if any(ip_address(entry[4][0]) in network for network in LAN_NETWORKS)
    ]
    if not allowed or len(allowed) != len(addresses):
        raise HTTPException(
            422, "Der Kamerahost muss auf eine private LAN-Adresse zeigen."
        )

    connection = (HTTPSConnection if secure else HTTPConnection)(
        parts.hostname, port, timeout=TIMEOUT
    )
    # Pin the validated IP while retaining the URL hostname for Host and TLS verification.
    connection._create_connection = lambda addr, timeout, source: (
        socket.create_connection((allowed[0], addr[1]), timeout, source)
    )
    path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
    try:
        accept = "image/jpeg" if mode == "jpeg" else "multipart/x-mixed-replace"
        connection.request("GET", path, headers={"Accept": accept})
        response = connection.getresponse()
        media_type = Message()
        media_type["Content-Type"] = response.getheader("Content-Type", "")
        if mode == "jpeg":
            if response.status == 200 and media_type.get_content_type() == "image/jpeg":
                return connection, response, "image/jpeg"
            response.close()
            raise HTTPException(502, "Die Kamera liefert kein JPEG-Einzelbild.")
        boundary = media_type.get_boundary()
        if (
            response.status != 200
            or media_type.get_content_type() != "multipart/x-mixed-replace"
            or not boundary
            or not re.fullmatch(r"[A-Za-z0-9'()+_,./:=? -]{1,70}", boundary)
        ):
            response.close()
            raise HTTPException(502, "Die Kamera liefert keinen MJPEG-Stream.")
        content_type = f'multipart/x-mixed-replace; boundary="{boundary}"'
        return connection, response, content_type
    except BaseException:
        connection.close()
        raise


@router.get("/stream")
def camera_stream(request: Request):
    if not principal(request) or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Anmeldung für das Kamerabild erforderlich.")
    if request.headers.get("sec-fetch-dest") not in (None, "image"):
        raise HTTPException(403, "Der Stream ist nur als Kamerabild verfügbar.")
    config = camera_settings()
    if not config.enabled or paused():
        raise HTTPException(404, "Kamera ist derzeit nicht verfügbar.")
    if not STREAM_SLOTS.acquire(blocking=False):
        raise HTTPException(503, "Zu viele offene Kamerastreams.")
    try:
        connection, response, content_type = open_camera(
            endpoint(config.url), config.mode
        )
    except (OSError, UpstreamError):
        STREAM_SLOTS.release()
        raise HTTPException(502, "Kamera ist nicht erreichbar.") from None
    except BaseException:
        STREAM_SLOTS.release()
        raise

    def close_stream():
        try:
            response.close()
        finally:
            try:
                connection.close()
            finally:
                STREAM_SLOTS.release()

    if config.mode == "jpeg":
        try:
            image = response.read(MAX_JPEG_BYTES + 1)
            if len(image) > MAX_JPEG_BYTES or not image.startswith(b"\xff\xd8"):
                raise HTTPException(502, "Ungültiges oder zu großes JPEG-Einzelbild.")
            return Response(image, media_type=content_type, headers=IMAGE_HEADERS)
        except (OSError, UpstreamError):
            raise HTTPException(
                502, "Kamerabild konnte nicht gelesen werden."
            ) from None
        finally:
            close_stream()

    async def chunks():
        try:
            while not paused() and camera_settings() == config:
                block = await anyio.to_thread.run_sync(response.read1, 65536)
                if not block:
                    break
                yield block
        except (OSError, UpstreamError):
            return

    return CameraStream(
        chunks(),
        media_type=content_type,
        headers=IMAGE_HEADERS,
        release=close_stream,
    )
