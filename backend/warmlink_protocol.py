"""LTE framing, quiet windows and response correlation; no socket ownership or cache."""

import socket
import time

from backend.bus_stream import ModbusResponseTimeout
from backend.rtu import with_crc
from backend.warmlink_frames import find_frames, next_frame_pos
from backend.diagnostics import log_event


class WarmlinkSession:
    def __init__(
        self, sock, endpoint, *, on_frames=None, on_read=None, on_observed_read=None
    ):
        self.sock, self.endpoint = sock, endpoint
        self.on_frames = on_frames
        self.on_read = on_read
        self.on_observed_read = on_observed_read
        self.buffer = bytearray()
        self.poisoned = False
        self.last_received = 0.0
        self.foreign_pending = None
        self.foreign_since = 0.0
        self.foreign_ambiguous = False
        self.inflight_request = None

    def _expire_foreign_read(self):
        """Forget correlation only after the foreign response window has passed.

        A timed-out or overlapping foreign request is not a permanent bus lease.
        Expiration never accepts a response or skips quiet()/CRC validation.
        """
        if (
            self.foreign_pending
            and time.monotonic() - self.foreign_since > self.endpoint.timeout
        ):
            self.foreign_pending = None
            self.foreign_ambiguous = False
            self.foreign_since = 0.0
            log_event(
                "lte",
                "Antwortzeitfenster der fremden FC3-Abfrage abgelaufen; Zuordnung verworfen",
            )

    def receive(self, timeout):
        self._expire_foreign_read()
        self.sock.settimeout(max(0.001, timeout))
        try:
            data = self.sock.recv(4096)
        except socket.timeout:
            self._expire_foreign_read()
            return []
        if not data:
            raise ConnectionError("LTE-Verbindung geschlossen")
        self.last_received = time.monotonic()
        self._expire_foreign_read()
        self.buffer.extend(data)
        frames = find_frames(self.buffer, 125)
        if len(self.buffer) > 4096:
            raise ValueError("LTE-Stream nicht synchronisiert")
        log_event(
            "lte-rx",
            f"LTE RX: {len(data)} Bytes, {len(frames)} gültige Frames, {len(self.buffer)} Restbytes",
        )
        if self.on_frames:
            self.on_frames(frames)
        for f in frames:
            if f[0] != self.endpoint.slave:
                continue
            if f[9] == "read-request" and f[6] != self.inflight_request:
                self.foreign_ambiguous = self.foreign_pending is not None
                self.foreign_pending = (f[2], f[3])
                self.foreign_since = time.monotonic()
                log_event(
                    "lte-observed",
                    f"Beobachtete FC3-Anfrage: MAIN {f[2]}, Anzahl {f[3]}",
                )
            elif (
                f[9] == "read-response"
                and self.foreign_pending
                and f[3] == self.foreign_pending[1] * 2
            ):
                if not self.foreign_ambiguous:
                    if time.monotonic() - self.foreign_since <= self.endpoint.timeout:
                        words = [
                            int.from_bytes(f[4][i : i + 2], "big")
                            for i in range(0, f[3], 2)
                        ]
                        if self.on_observed_read:
                            self.on_observed_read(self.foreign_pending[0], words)
                    self.foreign_pending = None
        return frames

    def quiet(self):
        if self.poisoned:
            raise ValueError("LTE-Verbindung nach unklarer Antwort gesperrt")
        deadline = time.monotonic() + self.endpoint.timeout
        quiet_since = time.monotonic()
        foreign_read = self.foreign_pending is not None
        while time.monotonic() < deadline:
            frames = self.receive(0.1)
            quiet_since = max(quiet_since, self.last_received)
            foreign_read = self.foreign_pending is not None
            if time.monotonic() - quiet_since >= 0.8:
                if foreign_read:
                    raise ValueError("Fremde LTE-Leseabfrage noch unbeantwortet")
                if self.buffer and next_frame_pos(self.buffer, -1) >= 0:
                    # Preserve a real incomplete candidate through the full
                    # deadline. TCP can split a complete RTU frame arbitrarily.
                    continue
                if self.buffer:
                    log_event(
                        "lte", "LTE-Restbytes ohne Frameanfang nach Ruhephase verworfen"
                    )
                self.buffer.clear()
                return
        raise TimeoutError("LTE-Bus belegt; kein Telegramm gesendet")

    def exchange(self, request, mode, register, count):
        self.quiet()
        self.inflight_request = request
        log_event("lte", f"LTE TX: {mode}, MAIN {register}, Anzahl {count}")
        self.sock.sendall(request)
        deadline = time.monotonic() + self.endpoint.timeout
        try:
            while time.monotonic() < deadline:
                for f in self.receive(min(0.1, deadline - time.monotonic())):
                    slave, func, start, length, payload, _, raw, _, _, kind = f
                    if slave != self.endpoint.slave:
                        continue
                    if raw == request:
                        continue  # local TX echo
                    if kind == "read-request":
                        raise ValueError(
                            "Konkurrierende DTU-Abfrage; LTE-Antwort nicht eindeutig"
                        )
                    if mode == "read" and kind == "read-response":
                        if length != count * 2:
                            raise ValueError(
                                "LTE-Antwort gehört nicht zur aktuellen Anfrage"
                            )
                        log_event(
                            "lte",
                            f"LTE RX: MAIN {register}, Anzahl {count}, CRC gültig",
                        )
                        return [
                            int.from_bytes(payload[i : i + 2], "big")
                            for i in range(0, length, 2)
                        ]
                    if (
                        mode == "write"
                        and kind == "write-response"
                        and start == register
                        and length == count
                    ):
                        log_event("lte", f"LTE Schreib-ACK: MAIN {register}")
                        return []
            raise ModbusResponseTimeout(self.endpoint.medium)
        except (OSError, ValueError):
            log_event(
                "lte-error", "LTE-Antwort unklar oder Timeout; Verbindung gesperrt"
            )
            self.poisoned = True
            raise
        finally:
            self.inflight_request = None

    def read_holding(self, register, count=1):
        if not 0 <= register <= 65535 or not 1 <= count <= 125:
            raise ValueError("Ungültiger LTE-Registerbereich")
        body = (
            bytes((self.endpoint.slave, 3))
            + register.to_bytes(2, "big")
            + count.to_bytes(2, "big")
        )
        words = self.exchange(with_crc(body), "read", register, count)
        if self.on_read:
            self.on_read(register, words)
        return words

    def write_one(self, register, raw):
        # Same FC16 single-word format as Desktop build_write_frame.
        body = (
            bytes((self.endpoint.slave, 16))
            + register.to_bytes(2, "big")
            + b"\x00\x01\x02"
            + raw.to_bytes(2, "big")
        )
        self.exchange(with_crc(body), "write", register, 1)
