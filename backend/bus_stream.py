"""Byte-stream adapter. Only the physical link differs between TCP and USB."""

import os
import socket
import stat
from time import monotonic, sleep

from backend.settings import SERIAL_DEVICE


class SerialStream:
    def __init__(self, port, baudrate):
        self.port = port
        self.gap = max(0.00175, 35 / baudrate)
        self.last_activity = 0.0

    def recv(self, size):
        data = self.port.read(min(size, max(1, self.port.in_waiting)))
        if not data:
            raise socket.timeout("Keine seriellen Daten")
        self.last_activity = monotonic()
        return data

    def sendall(self, payload):
        remaining = self.gap - (monotonic() - self.last_activity)
        if remaining > 0:
            sleep(remaining)
        if self.port.write(payload) != len(payload):
            raise TimeoutError("Serielles Telegramm unvollständig gesendet")
        self.port.flush()
        self.last_activity = monotonic()

    def settimeout(self, value):
        self.port.timeout = value

    def fileno(self):
        return self.port.fileno() if self.port.is_open else -1

    def shutdown(self, _direction):
        if self.port.is_open:
            self.port.cancel_read()

    def close(self):
        self.port.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def connect_bus(endpoint, socket_factory=None):
    if endpoint.medium == "tcp":
        factory = socket_factory or socket.create_connection
        return factory((endpoint.host, endpoint.port), timeout=endpoint.timeout)

    import serial

    path = endpoint.serial_device
    try:
        if not SERIAL_DEVICE.fullmatch(path) or not stat.S_ISCHR(os.stat(path).st_mode):
            raise ValueError("Kein freigegebenes serielles Gerät")
        port = serial.Serial(
            path,
            baudrate=endpoint.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=endpoint.timeout,
            write_timeout=endpoint.timeout,
            exclusive=True,
        )
    except (OSError, ValueError):
        raise OSError(
            "USB-RS485-Gerät fehlt, ist belegt oder nicht zugänglich"
        ) from None
    return SerialStream(port, endpoint.baudrate)
