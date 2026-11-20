"""Direct LAN access for the Docker LAN configuration."""

from ipaddress import IPv4Address, IPv4Network
import os
import re
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


def hostname(host):
    try:
        authority = urlsplit("//" + host)
        if (
            authority.path
            or authority.query
            or authority.fragment
            or authority.username is not None
        ):
            return None
        return authority.hostname
    except ValueError:
        return None


def allowed(peer, host):
    if peer not in LOOPBACK_NAMES and not private_ipv4(peer):
        return False
    target = hostname(host)
    if target is None:
        return False
    configured_hosts = {
        name.strip().lower().rstrip(".")
        for name in os.getenv("FOXAIR_LAN_HOSTS", "").split(",")
        if name.strip()
    }
    if private_ipv4(target) or target.rstrip(".") in configured_hosts:
        return True
    if target in LOOPBACK_NAMES:
        return peer in LOOPBACK_NAMES

    from backend import cloud_config, setup

    if setup.required():
        # Any valid DNS hostname can start LAN setup. Require a real private peer.
        name = target.rstrip(".")
        return (
            len(name) <= 253
            and any(c.isalpha() for c in name)
            and all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in name.split(".")
            )
        )
    return target == cloud_config._read_json(cloud_config.ADMIN_FILE).get(
        "setup_lan_hostname"
    )


def direct_http(request):
    peer = request.scope.get("foxair.tcp_peer")
    return (
        enabled()
        and request.url.scheme == "http"
        and allowed(peer, request.headers.get("host", ""))
    )
