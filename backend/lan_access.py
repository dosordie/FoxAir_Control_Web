"""Direct LAN access for the Docker LAN configuration."""

from ipaddress import IPv4Address, IPv4Network
import os
from urllib.parse import urlsplit

PRIVATE_NETWORKS = tuple(
    IPv4Network(block) for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
LOOPBACK_NAMES = ("localhost", "127.0.0.1", "::1")


def enabled():
    return os.getenv("FOXAIR_CONTAINER") == "1" and os.getenv("FOXAIR_LAN_HTTP") == "1"


def private_ipv4(value):
    try:
        address = IPv4Address(value)
    except (ValueError, TypeError):
        return False
    return any(address in network for network in PRIVATE_NETWORKS)


def allowed(peer, host):
    try:
        authority = urlsplit("//" + host)
        if (
            authority.path
            or authority.query
            or authority.fragment
            or authority.username is not None
        ):
            return False
        target = authority.hostname
    except ValueError:
        return False
    configured_hosts = {
        name.strip().lower().rstrip(".")
        for name in os.getenv("FOXAIR_LAN_HOSTS", "").split(",")
        if name.strip()
    }
    target_allowed = private_ipv4(target) or (
        target is not None and target.rstrip(".") in configured_hosts
    )
    if peer in LOOPBACK_NAMES:
        return target in LOOPBACK_NAMES or target_allowed
    return private_ipv4(peer) and target_allowed


def direct_http(request):
    peer = request.scope.get("foxair.tcp_peer")
    return (
        enabled()
        and request.url.scheme == "http"
        and allowed(peer, request.headers.get("host", ""))
    )
