"""Supported SSO entry point: preserve the actual TCP peer before app dispatch."""

import argparse
import uvicorn
from backend.main import app
from backend import lan_access
from starlette.responses import PlainTextResponse


class TCPPeerApp:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        if scope["type"] in ("http", "websocket"):
            scope["foxair.tcp_peer"] = (scope.get("client") or (None,))[0]
        if scope["type"] == "http" and lan_access.enabled():
            hosts = [
                value.decode("latin-1")
                for key, value in scope["headers"]
                if key == b"host"
            ]
            if len(hosts) != 1 or not lan_access.allowed(
                scope["foxair.tcp_peer"], hosts[0]
            ):
                message = (
                    "FoxAir: Dieser Hostname ist noch nicht freigegeben. "
                    "FoxAir über die private LAN-IP öffnen und den Namen als Administrator "
                    "unter Einstellungen → Webzugriff eintragen."
                    if lan_access.private_peer(scope["foxair.tcp_peer"])
                    else "FoxAir: Direkter HTTP-Zugriff ist nur aus privaten IPv4-Netzen möglich."
                )
                await PlainTextResponse(message, status_code=403)(scope, receive, send)
                return
        await self.application(scope, receive, send)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()
    # Never let Uvicorn replace scope.client using user-controlled X-Forwarded-For.
    uvicorn.run(
        TCPPeerApp(app),
        host=args.host,
        port=args.port,
        proxy_headers=False,
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()
