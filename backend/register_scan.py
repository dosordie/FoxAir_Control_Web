"""One cancellable FC03 initialization job shared by all browsers."""

from dataclasses import asdict, dataclass
import threading
import time
from typing import Literal

from backend.settings import Endpoint, warmlink_endpoint
from backend.warmlink import open_warmlink
from backend.register_definitions import LTE_INIT_BLOCKS

BLOCKS = LTE_INIT_BLOCKS


@dataclass
class ScanState:
    status: Literal["idle", "running", "complete", "partial", "error"] = "idle"
    completed: int = 0
    total: int = len(BLOCKS)
    error: str | None = None


class RegisterScan:
    def __init__(
        self, *, endpoint_provider=warmlink_endpoint, connection_factory=open_warmlink
    ):
        self._endpoint_provider = endpoint_provider
        self._connection_factory = connection_factory
        self._lock = threading.RLock()
        self._state = ScanState()
        self._source: Endpoint | None = None
        self._finished = 0.0
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        endpoint = self._endpoint_provider()
        with self._lock:
            return asdict(self._state if self._source == endpoint else ScanState())

    def _run(self, endpoint: Endpoint) -> None:
        try:
            with self._connection_factory(endpoint) as client:
                for start, count in BLOCKS:
                    if self._cancel.is_set() or self._endpoint_provider() != endpoint:
                        raise ValueError("scan cancelled or source changed")
                    words = client.read_holding(start, count)
                    if len(words) != count:
                        raise ValueError("incomplete read")
                    with self._lock:
                        self._state.completed += 1
            with self._lock:
                self._state.status = "complete"
                self._state.error = None
        except (OSError, ValueError):
            with self._lock:
                self._state.status = "partial" if self._state.completed else "error"
                self._state.error = "LTE-Blockabfrage abgebrochen; bestätigte Teilwerte bleiben erhalten. Kein automatischer Wiederholungsversuch."
        finally:
            with self._lock:
                self._finished = time.monotonic()

    def start(self) -> dict:
        endpoint = self._endpoint_provider()
        if endpoint is None:
            raise ValueError("LTE-Anschluss noch nicht aktiviert")
        with self._lock:
            if self._state.status == "running" or (
                self._thread and self._thread.is_alive()
            ):
                return {**self.status(), "started": False}
            if self._source == endpoint and time.monotonic() - self._finished < 30:
                return {**self.status(), "started": False}
            self._source = endpoint
            self._cancel.clear()
            self._state = ScanState(status="running")
            self._thread = threading.Thread(
                target=self._run,
                args=(endpoint,),
                daemon=True,
                name="lte-register-scan",
            )
            self._thread.start()
            return {**self.status(), "started": True}

    def stop(self, timeout: float = 2.0) -> bool:
        """Do not send another block after shutdown; do not repeat an in-flight read."""
        self._cancel.set()
        with self._lock:
            thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
        return thread is None or not thread.is_alive()


scan = RegisterScan()


def status():
    return scan.status()


def start():
    return scan.start()


def stop():
    return scan.stop()
