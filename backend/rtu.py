"""Minimal Modbus-RTU-over-raw-TCP transport for an explicit ser2net endpoint.

Intended only for a dedicated standard Modbus bus. Do NOT use this generic
request/response client on an existing Display/LTE multi-master bus.
"""

from contextlib import contextmanager
from functools import wraps
import socket
import threading
import time

from backend.settings import Endpoint
from backend.bus_locks import endpoint_lock
from backend.bus_stream import ModbusResponseTimeout, bus_error_message, connect_bus
from backend.diagnostics import log_event


def crc16(payload: bytes) -> int:
    crc = 0xFFFF
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else crc >> 1
    return crc


def with_crc(payload: bytes) -> bytes:
    return payload + crc16(payload).to_bytes(2, "little")


def read_exact(sock: socket.socket, size: int) -> bytes:
    received = bytearray()
    while len(received) < size:
        chunk = sock.recv(size - len(received))
        if not chunk:
            raise ConnectionError(
                "RTU-Verbindung vor vollständigem Telegramm geschlossen"
            )
        received.extend(chunk)
    return bytes(received)


def _rtu_exchange(method):
    @wraps(method)
    def exchange(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except (OSError, ValueError) as error:
            self.poisoned = True
            if isinstance(error, ConnectionError):
                log_event("standard-error", bus_error_message(error, ""))
            raise

    return exchange


class RtuReadSession:
    def __init__(self, sock: socket.socket, slave: int, medium: str = "tcp"):
        self.sock = sock
        self.slave = slave
        self.medium = medium
        self.poisoned = False

    def _read_response(self, size):
        try:
            return read_exact(self.sock, size)
        except TimeoutError as error:
            failure = ModbusResponseTimeout(self.medium)
            log_event("standard-error", str(failure))
            raise failure from error

    @_rtu_exchange
    def read_holding(self, register: int, count: int = 1) -> list[int]:
        if (
            not 0 <= register <= 65535
            or not 1 <= count <= 125
            or register + count > 65536
        ):
            raise ValueError("Ungültiger Registerbereich")
        request = (
            bytes((self.slave, 0x03))
            + register.to_bytes(2, "big")
            + count.to_bytes(2, "big")
        )
        self.sock.sendall(with_crc(request))
        header = self._read_response(3)
        if header[0] != self.slave:
            raise ValueError("Unerwartete Modbus-Slaveadresse")
        if header[1] == 0x83:
            frame = header + self._read_response(2)
            if crc16(frame[:-2]) != int.from_bytes(frame[-2:], "little"):
                raise ValueError("CRC-Fehler in Modbus-Exception")
            raise ValueError("Modbus-Exception " + str(header[2]))
        if header[1] != 0x03 or header[2] != count * 2:
            raise ValueError("Unerwartete Modbus-Antwort")
        frame = header + self._read_response(header[2] + 2)
        if crc16(frame[:-2]) != int.from_bytes(frame[-2:], "little"):
            raise ValueError("CRC-Fehler")
        return [
            int.from_bytes(frame[3 + i : 5 + i], "big") for i in range(0, count * 2, 2)
        ]

    @_rtu_exchange
    def write_one(self, register: int, raw: int):
        if not 0 <= register <= 65535 or not 0 <= raw <= 65535:
            raise ValueError("Ungültiges Registerwort")
        body = (
            bytes((self.slave, 16))
            + register.to_bytes(2, "big")
            + b"\x00\x01\x02"
            + raw.to_bytes(2, "big")
        )
        self.sock.sendall(with_crc(body))
        header = self._read_response(2)
        frame = header + self._read_response(3 if header[1] & 128 else 6)
        if crc16(frame[:-2]) != int.from_bytes(frame[-2:], "little"):
            raise ValueError("CRC-Fehler im Schreib-ACK")
        expected = bytes((self.slave, 16)) + register.to_bytes(2, "big") + b"\x00\x01"
        if frame[:-2] != expected:
            raise ValueError("Modbus-Schreibantwort nicht bestätigt")


class StandardConnection:
    """Reuse the RTU socket while a browser renews its lease."""

    def __init__(self):
        self._lock = threading.RLock()
        self._socket = None
        self._endpoint = None
        self._until = 0.0
        self._expiry = None

    def _close(self):
        if self._socket is not None:
            self._socket.close()
        self._socket = self._endpoint = None

    def disconnect(self):
        with self._lock:
            self._until = 0.0
            if self._expiry:
                self._expiry.cancel()
                self._expiry = None
            self._close()

    def _expire(self, timer):
        with self._lock:
            if self._expiry is not timer:
                return
            self._expiry = None
            remaining = self._until - time.monotonic()
            if remaining > 0:
                self._schedule_expiry(remaining)
            else:
                self._close()

    def _schedule_expiry(self, delay):
        timer = threading.Timer(delay, lambda: self._expire(timer))
        timer.daemon = True
        self._expiry = timer
        timer.start()

    def lease(self, seconds):
        with self._lock:
            self._until = time.monotonic() + seconds
            if self._expiry is None:
                self._schedule_expiry(seconds)

    @contextmanager
    def session(self, endpoint):
        with self._lock, endpoint_lock(endpoint):
            if self._endpoint != endpoint or self._until <= time.monotonic():
                self._close()
            if self._socket is None:
                self._socket = connect_bus(endpoint, transport="standard")
                self._endpoint = endpoint
            session = RtuReadSession(self._socket, endpoint.slave, endpoint.medium)
            try:
                yield session
            except BaseException:
                # A failed or incomplete RTU exchange can leave bytes queued.
                self._close()
                raise
            finally:
                if session.poisoned or self._until <= time.monotonic():
                    self._close()


standard_connection = StandardConnection()


@contextmanager
def open_rtu(endpoint: Endpoint):
    from backend.transport_selection import operation

    with operation("standard_modbus"), standard_connection.session(endpoint) as session:
        yield session
