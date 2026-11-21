"""One socket owner for the display bus; passive unless explicitly synchronized."""

import socket
import threading
import time
from backend.display_protocol import DisplayProtocol
from backend.bus_stream import connect_bus
from backend.diagnostics import log_event
from backend.settings import display_endpoint, local_bus_config
from backend.last_values import remember_words, store
from backend.transport_selection import LOCK as selection_lock, allows, operation


class DisplayBus:
    def __init__(self):
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.endpoint = None
        self.sock = None
        self.connected = False
        self.last_rx = None
        self.error = None
        self.lease_until = 0
        self.protocol = None
        self.words = {}
        self.source_epoch = 0
        self.handover_closed = False

    def lease(self):
        with self.lock:
            self.lease_until = (
                time.monotonic()
                + local_bus_config("display_modbus")["browser_timeout_seconds"]
            )

    def disconnect(self):
        with self.lock:
            self.handover_closed = True
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.sock.close()
                self.sock = None
            self.connected = False
            if self.protocol and self.protocol.sync["status"] == "running":
                self.protocol.sync.update(
                    status="error", error="Verbindungsart gewechselt"
                )

    def connect(self, endpoint):
        with operation("display_modbus"):
            sock = connect_bus(endpoint)
            with self.lock:
                self.sock = sock
            return sock

    def stop(self):
        self.stop_event.set()
        with self.lock:
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        if self.thread:
            self.thread.join(timeout=3)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self.run, daemon=True, name="foxair-display"
        )
        self.thread.start()

    def state(self):
        with self.lock:
            scan = (
                dict(self.protocol.sync)
                if self.protocol
                else {"status": "idle", "completed": 0, "total": 6, "error": None}
            )
            return {
                "connected": self.connected
                and self.endpoint == display_endpoint()
                and allows("display_modbus"),
                "mode": local_bus_config("display_modbus")["connection_mode"],
                "error": self.error,
                "last_rx": self.last_rx,
                "lease_seconds": max(0, int(self.lease_until - time.monotonic())),
                "scan": scan,
                "source_epoch": self.source_epoch,
            }

    def synchronize(self):
        self.lease()
        with operation("display_modbus"), self.lock:
            if (
                not self.connected
                or not self.protocol
                or self.endpoint != display_endpoint()
            ):
                raise ValueError("Display-Verbindung noch nicht bereit")
            result = self.protocol.start()
            log_event("display-sync", "Display-Parametersynchronisation angefordert")
            return result

    def values(self):
        with self.lock:
            endpoint = self.endpoint
            if endpoint is None or endpoint != display_endpoint():
                return {}
            keys = set(self.words)
        result = store.values()
        return {
            key: {
                **row,
                "quality": "observed"
                if self.connected and row.get("quality") != "stale"
                else "stale",
            }
            for key, row in result.items()
            if int(key) in keys and row.get("transport") == "display_modbus"
        }

    def run(self):
        while not self.stop_event.is_set():
            endpoint = display_endpoint()
            config = local_bus_config("display_modbus")
            wanted = (
                endpoint
                and allows("display_modbus")
                and (
                    config["connection_mode"] == "permanent"
                    or time.monotonic() < self.lease_until
                )
            )
            if not wanted:
                self.stop_event.wait(0.5)
                continue
            try:
                with self.connect(endpoint) as sock:
                    sock.settimeout(0.01)
                    with selection_lock, self.lock:
                        if not allows("display_modbus") or sock.fileno() < 0:
                            raise ValueError("Verbindung gewechselt")
                        self.endpoint = endpoint
                        self.sock = sock
                        self.connected = True
                        self.handover_closed = False
                        self.error = None
                        self.words = {}
                        self.source_epoch += 1
                        epoch = self.source_epoch

                        def remember(start, words):
                            if (
                                self.endpoint != endpoint
                                or self.source_epoch != epoch
                                or display_endpoint() != endpoint
                            ):
                                return
                            self.words.update(
                                {start + i: word for i, word in enumerate(words)}
                            )
                            remember_words(
                                endpoint, start, words, transport="display_modbus"
                            )

                        self.protocol = DisplayProtocol(remember)
                    log_event("display", "Display-Bus verbunden; passiver Empfang")
                    while (
                        not self.stop_event.is_set()
                        and endpoint == display_endpoint()
                        and allows("display_modbus")
                    ):
                        if (
                            local_bus_config("display_modbus")["connection_mode"]
                            != "permanent"
                            and time.monotonic() >= self.lease_until
                        ):
                            break
                        try:
                            data = sock.recv(4096)
                        except socket.timeout:
                            data = None
                        if data == b"":
                            raise ConnectionError("Display-Verbindung geschlossen")
                        with selection_lock, self.lock:
                            if not allows("display_modbus"):
                                break
                            if data:
                                self.last_rx = time.time()
                                count = self.protocol.feed(data)
                                if count:
                                    log_event(
                                        "display-rx",
                                        "Display-Telegramme CRC-geprüft",
                                        count=count,
                                    )
                            from backend.settings import _config_lock

                            with _config_lock:
                                if display_endpoint() != endpoint:
                                    break
                                command = self.protocol.tick()
                                if command:
                                    sock.sendall(command)
                            if command:
                                log_event(
                                    "display-sync",
                                    "Festes Display-Snapshot-Steuertelegramm gesendet",
                                )
            except (OSError, ValueError):
                with self.lock:
                    unexpected = (
                        not self.handover_closed
                        and not self.stop_event.is_set()
                        and allows("display_modbus")
                    )
                    self.error = (
                        "Display-Verbindung unterbrochen oder nicht erreichbar"
                        if unexpected
                        else None
                    )
                if unexpected:
                    log_event(
                        "display-error",
                        "Display-Verbindung unterbrochen; erneuter passiver Verbindungsversuch",
                    )
            finally:
                with self.lock:
                    if self.protocol and self.protocol.sync["status"] == "running":
                        self.protocol.sync.update(
                            status="error",
                            error="Verbindung während Display-Abfrage beendet",
                        )
                    self.connected = False
                    self.sock = None
            self.stop_event.wait(2)


manager = DisplayBus()
