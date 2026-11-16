"""On-demand LTE RTU stream operations with foreign-master collision detection.

There is no physical multi-master arbitration on RS485. We wait for quiet,
drain existing traffic, serialize our requests, reject competing FC03 reads,
and close on every timeout/ambiguity. Never retry a write. FC16 unsolicited
blocks and local echoes are distinguished from responses by the stream parser.
"""
from contextlib import contextmanager
import socket
import threading
import time

from backend.rtu import with_crc, _bus_guard, _bus_locks
from backend.warmlink_frames import find_frames
from backend.cloud_state import log_event

_last_write = {}


class WarmlinkSession:
    def __init__(self, sock, endpoint):
        self.sock, self.endpoint = sock, endpoint
        self.buffer = bytearray()
        self.poisoned = False
        self.last_received = 0.0

    def receive(self, timeout):
        self.sock.settimeout(max(.001, timeout))
        try:
            data = self.sock.recv(4096)
        except socket.timeout:
            return []
        if not data:
            raise ConnectionError("LTE-Verbindung geschlossen")
        self.last_received = time.monotonic()
        self.buffer.extend(data)
        if len(self.buffer) > 4096:
            raise ValueError("LTE-Stream nicht synchronisiert")
        frames = find_frames(self.buffer, 125)
        log_event("lte-rx", f"LTE RX: {len(data)} Bytes, {len(frames)} gültige Frames, {len(self.buffer)} Restbytes")
        return frames

    def quiet(self):
        if self.poisoned:
            raise ValueError("LTE-Verbindung nach unklarer Antwort gesperrt")
        deadline = time.monotonic() + self.endpoint.timeout
        quiet_since = time.monotonic()
        foreign_read = False
        while time.monotonic() < deadline:
            frames = self.receive(.1)
            quiet_since = max(quiet_since, self.last_received)
            for f in frames:
                if f[0] == self.endpoint.slave and f[9] == "read-request":
                    foreign_read = True
                elif f[0] == self.endpoint.slave and f[9] == "read-response":
                    foreign_read = False
            if time.monotonic() - quiet_since >= .3:
                if foreign_read:
                    raise ValueError("Fremde LTE-Leseabfrage noch unbeantwortet")
                if self.buffer:
                    raise ValueError("Unvollständiger LTE-Verkehr; kein Telegramm gesendet")
                self.buffer.clear()
                return
        raise TimeoutError("LTE-Bus belegt; kein Telegramm gesendet")

    def exchange(self, request, mode, register, count):
        self.quiet()
        log_event("lte", f"LTE TX: {mode}, MAIN {register}, Anzahl {count}")
        self.sock.sendall(request)
        deadline = time.monotonic() + self.endpoint.timeout
        try:
            while time.monotonic() < deadline:
                for f in self.receive(min(.1, deadline - time.monotonic())):
                    slave, func, start, length, payload, _, raw, _, _, kind = f
                    if slave != self.endpoint.slave:
                        continue
                    if raw == request:
                        continue  # local TX echo
                    if kind == "read-request":
                        raise ValueError("Konkurrierende DTU-Abfrage; LTE-Antwort nicht eindeutig")
                    if mode == "read" and kind == "read-response":
                        if length != count * 2:
                            raise ValueError("LTE-Antwort gehört nicht zur aktuellen Anfrage")
                        log_event("lte", f"LTE RX: MAIN {register}, Anzahl {count}, CRC gültig")
                        return [int.from_bytes(payload[i:i+2], "big") for i in range(0, length, 2)]
                    if mode == "write" and kind == "write-response" and start == register and length == count:
                        log_event("lte", f"LTE Schreib-ACK: MAIN {register}")
                        return []
            raise TimeoutError("Keine eindeutige LTE-Antwort; kein automatischer Retry")
        except (OSError, ValueError):
            log_event("lte-error", "LTE-Antwort unklar oder Timeout; Verbindung gesperrt")
            self.poisoned = True
            raise

    def read_holding(self, register, count=1):
        if not 0 <= register <= 65535 or not 1 <= count <= 125:
            raise ValueError("Ungültiger LTE-Registerbereich")
        body = bytes((self.endpoint.slave, 3)) + register.to_bytes(2, "big") + count.to_bytes(2, "big")
        return self.exchange(with_crc(body), "read", register, count)

    def write_one(self, register, raw):
        # Same FC16 single-word format as Desktop build_write_frame.
        body = bytes((self.endpoint.slave, 16)) + register.to_bytes(2, "big") + b"\x00\x01\x02" + raw.to_bytes(2, "big")
        self.exchange(with_crc(body), "write", register, 1)


@contextmanager
def open_warmlink(endpoint):
    key = (endpoint.host, endpoint.port)
    with _bus_guard:
        lock = _bus_locks.setdefault(key, threading.Lock())
    with lock:
        try:
            with socket.create_connection(key, timeout=endpoint.timeout) as sock:
                log_event("lte", "LTE TCP verbunden; bedarfsgesteuerte Sitzung")
                try:
                    yield WarmlinkSession(sock, endpoint)
                finally:
                    log_event("lte", "LTE TCP-Sitzung beendet")
        except (OSError, ValueError) as exc:
            log_event("lte-error", "LTE-Abfrage abgebrochen: " + type(exc).__name__)
            raise


def write_control(code, requested, expected):
    from backend.settings import warmlink_endpoint
    from backend.cloud_write import _format_value, _number, WriteValidationError, WriteConflictError
    endpoint = warmlink_endpoint()
    if endpoint is None:
        raise WriteValidationError("LTE-Anschluss nicht aktiviert")
    desired, _ = _format_value(code, requested)
    register = {"Mode": 1012, "R02": 1158}[code]
    scale = 10 if code == "R02" else 1
    with open_warmlink(endpoint) as client:
        key = (endpoint.host, endpoint.port)
        if time.monotonic() - _last_write.get(key, -1000) < 5:
            raise WriteConflictError("Nächster LTE-Schreibvorgang frühestens nach fünf Sekunden")
        previous = _number(client.read_holding(register)[0]) / scale
        if previous != _number(expected):
            raise WriteConflictError("LTE-Wert inzwischen geändert; bitte neu lesen")
        if code == "R02":
            low, high = client.read_holding(1164, 2)
            if not 50 <= low <= high <= 700 or not low <= desired * 10 <= high:
                raise WriteValidationError("R02 außerhalb der frisch gelesenen LTE-R10/R11-Grenzen")
        if warmlink_endpoint() != endpoint:
            raise WriteConflictError("LTE-Anschluss während der Prüfung geändert")
        if previous == desired:
            return {"status": "unchanged", "confirmed": True, "code": code, "value": float(previous)}
        try:
            _last_write[key] = time.monotonic()
            client.write_one(register, int(desired * scale))
            time.sleep(.8)
            actual = _number(client.read_holding(register)[0]) / scale
        except (OSError, ValueError):
            return {"status": "unconfirmed", "confirmed": False, "code": code,
                    "message": "LTE-Schreibvorgang nicht bestätigt; Zustand neu lesen, nicht erneut senden"}
        return {"status": "confirmed" if actual == desired else "unconfirmed", "confirmed": actual == desired,
                "code": code, "value": float(actual), "message": "LTE-Readback ausgewertet"}
