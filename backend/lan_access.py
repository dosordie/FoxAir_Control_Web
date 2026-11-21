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


def private_peer(peer):
    return peer in LOOPBACK_NAMES or private_ipv4(peer)


def valid_dns_name(name):
    return (
        len(name) <= 253
        and any(char.isalpha() for char in name)
        and all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in name.split(".")
        )
    )


def normalize_hosts(names):
    result = []
    for value in names:
        name = value.strip().lower().rstrip(".")
        if not valid_dns_name(name) or name in LOOPBACK_NAMES:
            raise ValueError(
                "Bitte nur gültige Hostnamen ohne URL, Port oder Platzhalter eingeben."
            )
        if name not in result:
            result.append(name)
    return result


def configured_hosts():
    from backend import cloud_config

    environment = {
        name.strip().lower().rstrip(".")
        for name in os.getenv("FOXAIR_LAN_HOSTS", "").split(",")
        if name.strip()
    }
    setup_host = cloud_config._read_json(cloud_config.ADMIN_FILE).get(
        "setup_lan_hostname"
    )
    if isinstance(setup_host, str):
        name = setup_host.rstrip(".")
        if name not in LOOPBACK_NAMES and valid_dns_name(name):
            environment.add(name)
    return environment


def saved_hosts():
    from backend import cloud_config

    row = cloud_config._read_json(cloud_config.STATE_DIR / "lan-access.json")
    hosts = row.get("hosts")
    return hosts if isinstance(hosts, list) else []


def allowed(peer, host):
    if not private_peer(peer):
        return False
    target = hostname(host)
    if target is None:
        return False
    if target in LOOPBACK_NAMES:
        return peer in LOOPBACK_NAMES
    if private_ipv4(target):
        return True

    name = target.rstrip(".")
    if name in configured_hosts() or name in saved_hosts():
        return True

    from backend import setup

    return setup.required() and valid_dns_name(name)


def direct_http(request):
    peer = request.scope.get("foxair.tcp_peer")
    return (
        enabled()
        and request.url.scheme == "http"
        and allowed(peer, request.headers.get("host", ""))
    )
