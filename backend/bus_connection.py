"""Lifecycle owner for the LTE socket, browser lease and passive receiver.

Parsing lives in warmlink_protocol; values live in RegisterCache. All clients
share the public endpoint lock. Background receiving never transmits.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import socket
import threading
import time

from backend.bus_locks import endpoint_lock
from backend.diagnostics import log_event
from backend.register_cache import RegisterCache
from backend.settings import Endpoint, warmlink_config, warmlink_endpoint
from backend.warmlink_protocol import WarmlinkSession


@dataclass
class Connection:
    endpoint: Endpoint
    session: WarmlinkSession


class BusConnectionManager:
    def __init__(
        self,
        *,
        cache=None,
        endpoint_provider=warmlink_endpoint,
        config_provider=warmlink_config,
        socket_factory=None,
        session_factory=WarmlinkSession,
    ):
        self.cache = cache if cache is not None else RegisterCache()
        self._endpoint_provider = endpoint_provider
        self._config_provider = config_provider
        self._socket_factory = socket_factory or socket.create_connection
        self._session_factory = session_factory
        self._state_lock = threading.RLock()
        self._io = threading.RLock()
        self._connection: Connection | None = None
        self._lease_until = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._stopped = False
        self._state = {
            "connected": False,
            "mode": "on_demand",
            "error": None,
            "last_rx": None,
        }

    @property
    def connected(self) -> bool:
        with self._state_lock:
            return self._state["connected"]

    def wanted(self, mode: str, now: float | None = None) -> bool:
        with self._state_lock:
            return mode == "permanent" or (
                mode == "browser"
                and (time.monotonic() if now is None else now) < self._lease_until
            )

    def lease(self) -> dict:
        with self._state_lock:
            self._lease_until = time.monotonic() + 90
        self.start()
        return self.status()

    def status(self) -> dict:
        with self._state_lock:
            connection = self._connection
            state = {
                **self._state,
                "lease_seconds": max(0, round(self._lease_until - time.monotonic())),
            }
        client = connection.session if connection else None
        pending = client.foreign_pending if client else None
        state["pending_read"] = (
            {
                "register": pending[0],
                "count": pending[1],
                "age_seconds": round(time.monotonic() - client.foreign_since, 1),
                "ambiguous": client.foreign_ambiguous,
            }
            if pending
            else None
        )
        return state

    def _new_session(self, endpoint: Endpoint) -> WarmlinkSession:
        if self.cache.select_source(endpoint):
            with self._state_lock:
                self._state["last_rx"] = None
        sock = self._socket_factory(
            (endpoint.host, endpoint.port), timeout=endpoint.timeout
        )

        def observe(frames):
            self.cache.observe_frames(endpoint, frames)
            if frames:
                with self._state_lock:
                    self._state["last_rx"] = time.time()

        try:
            return self._session_factory(
                sock,
                endpoint,
                on_frames=observe,
                on_read=lambda start, words: self.cache.record(endpoint, start, words),
                on_observed_read=lambda start, words: self.cache.record(
                    endpoint, start, words, observed=True
                ),
            )
        except BaseException:
            sock.close()
            raise

    def _close(self) -> None:
        """Caller owns _io; never hold the state lock across socket operations."""
        with self._state_lock:
            connection, self._connection = self._connection, None
            self._state["connected"] = False
        if connection:
            connection.session.sock.close()

    def _connect(self, endpoint: Endpoint) -> WarmlinkSession:
        if self._connection and self._connection.endpoint != endpoint:
            self._close()
        if self._connection is None:
            session = self._new_session(endpoint)
            with self._state_lock:
                self._connection = Connection(endpoint, session)
        with self._state_lock:
            self._state.update(connected=True, error=None)
        return self._connection.session

    @contextmanager
    def operation(self, endpoint: Endpoint):
        """Use the shared socket; discard ambiguous sessions without replay."""
        with self._io, endpoint_lock(endpoint):
            if self._stopped:
                raise RuntimeError("LTE-Verbindungsverwaltung ist beendet")
            client = self._connect(endpoint)
            try:
                yield client
            except (OSError, ValueError):
                log_event(
                    "lte-error",
                    "LTE-Abfrage auf gemeinsamer Verbindung abgebrochen; kein automatischer Retry",
                )
                self._close()
                raise
            finally:
                if client.poisoned:
                    self._close()

    @contextmanager
    def open(self, endpoint: Endpoint):
        if self._stopped:
            raise RuntimeError("LTE-Verbindungsverwaltung ist beendet")
        mode = self._config_provider().get("connection_mode", "on_demand")
        if mode != "on_demand" or self.connected:
            self.start()
            with self.operation(endpoint) as client:
                yield client
            return
        with self._io, endpoint_lock(endpoint):
            if self._stopped:
                raise RuntimeError("LTE-Verbindungsverwaltung ist beendet")
            client = self._new_session(endpoint)
            log_event("lte", "LTE TCP verbunden; bedarfsgesteuerte Sitzung")
            try:
                yield client
            except (OSError, ValueError) as error:
                log_event(
                    "lte-error", "LTE-Abfrage abgebrochen: " + type(error).__name__
                )
                raise
            finally:
                client.sock.close()
                log_event("lte", "LTE TCP-Sitzung beendet")

    def _receive_once(self) -> float:
        """Return interruptible backoff; never transmit from the background."""
        endpoint = self._endpoint_provider()
        mode = self._config_provider().get("connection_mode", "on_demand")
        with self._state_lock:
            self._state["mode"] = mode
            previous = self._connection.endpoint if self._connection else None
        target = previous or endpoint
        if target is None or not self._io.acquire(timeout=0.1):
            return 0.15
        lock = endpoint_lock(target)
        if not lock.acquire(timeout=0.1):
            self._io.release()
            return 0.15
        try:
            if (
                not endpoint
                or not self.wanted(mode)
                or (previous and endpoint != previous)
            ):
                self._close()
            if endpoint and self.wanted(mode):
                self._connect(endpoint).receive(0.15)
            return 0.15
        except (OSError, ValueError):
            self._close()
            with self._state_lock:
                self._state["error"] = (
                    "LTE-Verbindung unterbrochen; erneuter Verbindungsversuch"
                )
            log_event("lte-error", "Dauerverbindung unterbrochen; kein Schreib-Retry")
            return 2.0
        finally:
            lock.release()
            self._io.release()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._stop.wait(self._receive_once())
        finally:
            with self._io:
                self._close()

    def start(self) -> None:
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._stopped = False
            self._thread = threading.Thread(
                target=self._run, daemon=True, name="lte-connection"
            )
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> bool:
        """Stop receiving; close the socket only after the active operation."""
        self._stopped = True
        self._stop.set()
        with self._state_lock:
            thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
            if thread.is_alive():
                return False
        if not self._io.acquire(timeout=timeout):
            return False
        try:
            self._close()
            return True
        finally:
            self._io.release()


# One owner per application process; facades retain the stable HTTP API.
manager = BusConnectionManager()


def start():
    manager.start()


def stop():
    return manager.stop()


def status():
    return manager.status()


def lease():
    return manager.lease()


def observed_words():
    return manager.cache.observed_words()


def register_values(endpoint):
    return manager.cache.values(endpoint, connected=manager.connected)


def observed_metrics(fields, endpoint):
    return manager.cache.metrics(fields, endpoint, connected=manager.connected)
