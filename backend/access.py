"""Reader policy and durable, bounded write journal; never log credentials."""

import json
from datetime import datetime, timezone
import threading
from starlette.responses import JSONResponse
from backend import users, cloud_config

_LOCK = threading.Lock()


def record(user, path, payload, status, result=None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "path": path,
        "request": payload,
        "status": status,
        "result": result,
    }
    with _LOCK:
        path = cloud_config.STATE_DIR / "audit.json"
        data = cloud_config._read_json(path)
        items = data.get("items", [])
        cloud_config._atomic_json(path, {"items": ([entry] + items)[:1000]})


class AccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        from starlette.requests import Request

        request = Request(scope)
        path = scope["path"]
        if (
            not users.read().get("guest_read", True)
            and path
            not in (
                "/api/health",
                "/api/admin/session",
                "/api/admin/login",
                "/api/admin/sso/login",
                "/api/admin/logout",
            )
            and not users.principal(request)
        ):
            return await JSONResponse(
                {"detail": "Anmeldung erforderlich"}, status_code=401
            )(scope, receive, send)
        from backend.transport_selection import allows

        transport = request.query_params.get("transport")
        if path in ("/api/cloud/values", "/api/cloud/scan", "/api/cloud/write"):
            transport = "cloud"
        if transport and not allows(transport):
            return await JSONResponse(
                {
                    "detail": "Andere Verbindung ist global ausgewählt; Auswahl wird synchronisiert"
                },
                status_code=409,
            )(scope, receive, send)
        journal = request.method == "POST" and (
            path.startswith("/api/parameters/")
            and path.endswith("/write")
            or path
            in (
                "/api/cloud/write",
                "/api/warmlink/write",
                "/api/local/display_modbus/scan",
            )
            or path.startswith("/api/timers/")
        )
        if not journal:
            return await self.app(scope, receive, send)
        actor = users.principal(request)
        body = bytearray()
        result = bytearray()
        status = 500

        async def capture_receive():
            message = await receive()
            if message["type"] == "http.request" and len(body) < 65536:
                body.extend(message.get("body", b"")[: 65536 - len(body)])
            return message

        async def capture_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            if message["type"] == "http.response.body" and len(result) < 65536:
                result.extend(message.get("body", b"")[: 65536 - len(result)])
            await send(message)

        # Persist an intent before dispatch; if storage is unavailable no write is sent.
        try:
            record(
                actor["username"] if actor else "password-or-guest", path, {}, "started"
            )
        except OSError:
            return await JSONResponse(
                {"detail": "Änderungsprotokoll nicht verfügbar; kein Auftrag gesendet"},
                status_code=503,
            )(scope, receive, send)
        try:
            await self.app(scope, capture_receive, capture_send)
        finally:
            try:
                payload = json.loads(body)
                payload = {
                    k: payload[k]
                    for k in ("transport", "value", "expected", "code", "values")
                    if k in payload
                }
                response = json.loads(result)
                response = {
                    k: response[k]
                    for k in ("confirmed", "status", "value", "readback", "values")
                    if k in response
                }
            except (ValueError, TypeError):
                payload, response = {}, {}
            record(
                actor["username"] if actor else "password-or-guest",
                path,
                payload,
                status,
                response,
            )
