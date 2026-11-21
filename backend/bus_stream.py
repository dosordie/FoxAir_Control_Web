"""Byte-stream adapter. Only the physical link differs between TCP and USB."""

import os
import socket
import stat
from time import monotonic, sleep

from backend.diagnostics import log_event
from backend.settings import SERIAL_DEVICE


class BusOpenError(OSError):
    """The local transport could not be opened."""


class ModbusResponseTimeout(TimeoutError):
    def __init__(self, medium):
        message = "Keine vollständige Modbus-Antwort"
        if medium == "tcp":
            message = (
                "TCP verbunden, aber keine vollständige Modbus-Antwort. "
                "Möglicher Verbindungskonflikt, etwa durch einen zweiten Client am Gateway."
            )
        super().__init__(message)


def bus_error_message(error, fallback):
    if isinstance(error, (BusOpenError, ModbusResponseTimeout)):
        return str(error)
    if isinstance(error, ConnectionError):
        return "Verbindung nach dem Aufbau geschlossen oder unterbrochen"
    return fallback


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


def connect_bus(endpoint, socket_factory=None, *, transport):
    if endpoint.medium == "tcp":
        factory = socket_factory or socket.create_connection
        try:
            return factory((endpoint.host, endpoint.port), timeout=endpoint.timeout)
        except ConnectionRefusedError:
            message = "TCP-Verbindung abgelehnt. Port und Gateway prüfen."
        except TimeoutError:
            message = (
                "Zeitüberschreitung beim TCP-Verbindungsaufbau. "
                "Gateway nicht erreichbar oder möglicherweise ausgelastet."
            )
        except OSError:
            message = "TCP-Verbindung konnte nicht aufgebaut werden. Netzwerk, IP und Port prüfen."
        log_event(transport + "-error", message)
        raise BusOpenError(message)

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
        message = "USB-RS485-Gerät fehlt, ist belegt oder nicht zugänglich"
        log_event(transport + "-error", message)
        raise BusOpenError(message) from None
    return SerialStream(port, endpoint.baudrate)
