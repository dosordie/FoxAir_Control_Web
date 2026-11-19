"""Minimal Modbus-RTU-over-raw-TCP transport for an explicit ser2net endpoint.

Intended only for a dedicated standard Modbus bus. Do NOT use this generic
request/response client on an existing Display/LTE multi-master bus.
"""
from contextlib import contextmanager
import socket

from backend.settings import Endpoint
from backend.bus_locks import endpoint_lock

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
            raise ConnectionError("ser2net-Verbindung vor vollständigem Telegramm geschlossen")
        received.extend(chunk)
    return bytes(received)


class RtuReadSession:
    def __init__(self, sock: socket.socket, slave: int):
        self.sock = sock
        self.slave = slave

    def read_holding(self, register: int, count: int = 1) -> list[int]:
        if not 0 <= register <= 65535 or not 1 <= count <= 125 or register + count > 65536:
            raise ValueError("Ungültiger Registerbereich")
        request = bytes((self.slave, 0x03)) + register.to_bytes(2, "big") + count.to_bytes(2, "big")
        self.sock.sendall(with_crc(request))
        header = read_exact(self.sock, 3)
        if header[0] != self.slave:
            raise ValueError("Unerwartete Modbus-Slaveadresse")
        if header[1] == 0x83:
            frame = header + read_exact(self.sock, 2)
            if crc16(frame[:-2]) != int.from_bytes(frame[-2:], "little"):
                raise ValueError("CRC-Fehler in Modbus-Exception")
            raise ValueError("Modbus-Exception " + str(header[2]))
        if header[1] != 0x03 or header[2] != count * 2:
            raise ValueError("Unerwartete Modbus-Antwort")
        frame = header + read_exact(self.sock, header[2] + 2)
        if crc16(frame[:-2]) != int.from_bytes(frame[-2:], "little"):
            raise ValueError("CRC-Fehler")
        return [int.from_bytes(frame[3 + i:5 + i], "big") for i in range(0, count * 2, 2)]


    def write_one(self, register: int, raw: int):
        if not 0 <= register <= 65535 or not 0 <= raw <= 65535:
            raise ValueError("Ungültiges Registerwort")
        body = bytes((self.slave, 16)) + register.to_bytes(2, "big") + b"\x00\x01\x02" + raw.to_bytes(2, "big")
        self.sock.sendall(with_crc(body))
        header = read_exact(self.sock, 2)
        frame = header + read_exact(self.sock, 3 if header[1] & 128 else 6)
        if crc16(frame[:-2]) != int.from_bytes(frame[-2:], "little"):
            raise ValueError("CRC-Fehler im Schreib-ACK")
        expected = bytes((self.slave, 16)) + register.to_bytes(2, "big") + b"\x00\x01"
        if frame[:-2] != expected:
            raise ValueError("Modbus-Schreibantwort nicht bestätigt")


@contextmanager
def open_rtu(endpoint: Endpoint):
    """Exactly one client/operation at a time; socket always closes on exit."""
    from backend.transport_selection import operation
    with operation("standard_modbus"), endpoint_lock(endpoint):
        with socket.create_connection((endpoint.host, endpoint.port), timeout=endpoint.timeout) as sock:
            sock.settimeout(endpoint.timeout)
            yield RtuReadSession(sock, endpoint.slave)
