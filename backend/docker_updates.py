"""Read version and revision for the native Linux image behind GHCR latest."""

from functools import lru_cache
import json
import platform
from threading import Lock
from time import monotonic
from urllib.request import Request, urlopen

from backend.build_info import SEMVER, SHA

REGISTRY = "https://ghcr.io"
REPOSITORY = "dosordie/foxair-control-web"
ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
LOCK = Lock()


def _json(url, token=None):
    request = Request(url, headers={"Accept": ACCEPT, "User-Agent": "FoxAir-Web"})
    if token:
        # The registry can redirect blob reads to a signed CDN URL.
        request.add_unredirected_header("Authorization", "Bearer " + token)
    with urlopen(request, timeout=4) as response:
        data = response.read(262145)
    if len(data) > 262144:
        raise ValueError("Registry metadata too large")
    return json.loads(data)


def _digest(value):
    prefix, separator, digest = value.partition(":")
    if prefix != "sha256" or not separator or len(digest) != 64:
        raise ValueError("Invalid Docker digest")
    if any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Invalid Docker digest")
    return value


@lru_cache(maxsize=1)
def _cached_latest(_interval):
    try:
        token = _json(
            f"{REGISTRY}/token?service=ghcr.io&scope=repository:{REPOSITORY}:pull"
        )["token"]
        root = f"{REGISTRY}/v2/{REPOSITORY}"
        manifest = _json(root + "/manifests/latest", token)
        if "manifests" in manifest:
            architecture = {
                "x86_64": "amd64",
                "amd64": "amd64",
                "aarch64": "arm64",
                "arm64": "arm64",
            }.get(platform.machine().lower())
            descriptor = next(
                item
                for item in manifest["manifests"]
                if item.get("platform", {}).get("os") == "linux"
                and item.get("platform", {}).get("architecture") == architecture
            )
            manifest = _json(
                root + "/manifests/" + _digest(descriptor["digest"]), token
            )
        config = _json(root + "/blobs/" + _digest(manifest["config"]["digest"]), token)
        labels = config["config"]["Labels"]
        version = labels["org.opencontainers.image.version"]
        revision = labels["org.opencontainers.image.revision"]
        if SEMVER.fullmatch(version) and SHA.fullmatch(revision):
            return {"version": version, "source_commit": revision}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
        pass
    return None


def latest():
    with LOCK:
        return _cached_latest(int(monotonic() // 300))
