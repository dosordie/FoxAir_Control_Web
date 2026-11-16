"""CRC-checked LTE stream framing adapted from FoxAir_Control core (34ce0ed).

Preserves complete FC16 blocks and fragmented FC03 requests before resync.
"""
import struct
from backend.rtu import crc16
SUPPORTED_FUNCTIONS = {3, 6, 16}
MODBUS_FUNC_READ_HOLDING = 3
MODBUS_FUNC_WRITE_SINGLE = 6
MODBUS_FUNC_WRITE_MULTIPLE = 16
INCOMPLETE = object()
WORD_LEN_TYPES = {1001,1091,1181,1018,1101,1191,1271,1361,1451,1541,1461,1551,2001,2091}

def crc_check_frame(raw):
    actual = crc16(raw[:-2])
    expected = int.from_bytes(raw[-2:], 'little')
    return actual == expected, actual, expected

def is_possible_bus_addr(value: int) -> bool:
    # Modbus-RTU normale Slave-Adressen: 1..247.
    # 0 ist Broadcast. Auf dem Display-Bus werden die grossen zyklischen
    # Hauptdatenbloecke als FC16-Broadcast (Unit 0x00) gesendet; die muessen
    # fuer den Passiv-Logger sichtbar bleiben.
    # Warmlink nutzt hier bisher 0x63, wir lassen aber bewusst alle gueltigen
    # Adressen zu, damit andere Teilnehmer/Warmlink-Frames sichtbar werden.
    return 0 <= value <= 247


def is_frame_header_at(buf: bytearray, pos: int) -> bool:
    return (
        0 <= pos < len(buf) - 1
        and is_possible_bus_addr(buf[pos])
        and buf[pos + 1] in SUPPORTED_FUNCTIONS
    )


def next_frame_pos(buf: bytearray, start: int) -> int:
    # Suche nach beliebiger Bus-Adresse + unterstütztem Funktionscode.
    # Der simple Byte-Scan ist hier absichtlich robuster als find(0x10),
    # weil inzwischen auch FC03 auftaucht.
    for j in range(max(0, start + 1), len(buf) - 1):
        if is_frame_header_at(buf, j):
            return j
    return -1


def _ret(slave_addr: int, func: int, typ: int, length_field: int, payload: bytes,
         trailer: bytes, raw: bytes, j: int, end_frame: int, mode: str):
    return slave_addr, func, typ, length_field, payload, trailer, raw, j, end_frame, mode


def parse_frame_at(buf: bytearray, j: int, max_words: int = 512):
    n = len(buf)
    if n - j < 2:
        return INCOMPLETE
    slave_addr = buf[j]
    func = buf[j + 1]
    if not is_possible_bus_addr(slave_addr) or func not in SUPPORTED_FUNCTIONS:
        return None

    if func == MODBUS_FUNC_READ_HOLDING:
        # FC03 Request:  addr 03 start_hi start_lo qty_hi qty_lo crc_lo crc_hi
        # FC03 Response: addr 03 byte_count data... crc_lo crc_hi
        # Wichtig: Requests mit Startadresse 0x05xx sehen sonst wie eine
        # unvollstaendige Response mit byte_count=0x05 aus. Deshalb zuerst
        # das feste 8-Byte-Request-Format per CRC pruefen.
        if n - j >= 8:
            raw8 = bytes(buf[j:j + 8])
            if crc_check_frame(raw8)[0]:
                typ = struct.unpack_from(">H", raw8, 2)[0]
                quantity = struct.unpack_from(">H", raw8, 4)[0]
                if 1 <= quantity <= max_words:
                    payload = raw8[2:6]
                    trailer = raw8[6:8]
                    return _ret(slave_addr, func, typ, quantity, payload, trailer, raw8, j, j + 8, "read-request")

        if n - j < 5:
            return INCOMPLETE

        byte_count = buf[j + 2]
        if 0 < byte_count <= max_words * 2:
            end_frame = j + 3 + byte_count + 2
            if n < end_frame:
                return INCOMPLETE
            raw = bytes(buf[j:end_frame])
            if crc_check_frame(raw)[0]:
                payload = raw[3:3 + byte_count]
                trailer = raw[-2:]
                return _ret(slave_addr, func, 0, byte_count, payload, trailer, raw, j, end_frame, "read-response")

        if n - j < 8:
            return INCOMPLETE
        return None

    if func == MODBUS_FUNC_WRITE_SINGLE:
        # FC06 Request und Response haben identisches 8-Byte-Format:
        # addr 06 register value crc
        if n - j < 8:
            return INCOMPLETE
        raw8 = bytes(buf[j:j + 8])
        if crc_check_frame(raw8)[0]:
            typ = struct.unpack_from(">H", raw8, 2)[0]
            payload = raw8[4:6]
            trailer = raw8[6:8]
            return _ret(slave_addr, func, typ, 1, payload, trailer, raw8, j, j + 8, "write-single")
        return None

    if func != MODBUS_FUNC_WRITE_MULTIPLE:
        return None

    if n - j < 6:
        return INCOMPLETE

    typ = struct.unpack_from(">H", buf, j + 2)[0]
    quantity = struct.unpack_from(">H", buf, j + 4)[0]

    if quantity > max_words:
        return None

    # FC16 Request: addr 10 start qty byte_count data crc
    # Das deckt kurze Einzelwrites UND die grossen 90-Wort-Statusframes ab.
    if n - j >= 7:
        byte_count = buf[j + 6]
        if quantity > 0 and byte_count == quantity * 2 and byte_count <= max_words * 2:
            end_frame = j + 7 + byte_count + 2
            if n < end_frame:
                return INCOMPLETE
            raw = bytes(buf[j:end_frame])
            if not crc_check_frame(raw)[0]:
                # Meist kein echtes Frame, sondern z. B. eingebettetes "02 10 ..." im Payload.
                return None
            payload = raw[6:7 + byte_count]  # Bytecount + Daten
            trailer = raw[-2:]
            if quantity >= 16 and (typ in WORD_LEN_TYPES or byte_count == 0xB4):
                mode = "word-frame"
            elif quantity == 1:
                mode = "short-write"
            else:
                mode = "write-request"
            return _ret(slave_addr, func, typ, quantity, payload, trailer, raw, j, end_frame, mode)

    # FC16 Response/ACK: addr 10 start qty crc
    if n - j < 8:
        return INCOMPLETE
    raw8 = bytes(buf[j:j + 8])
    if crc_check_frame(raw8)[0]:
        payload = b""
        trailer = raw8[6:8]
        return _ret(slave_addr, func, typ, quantity, payload, trailer, raw8, j, j + 8, "write-response")

    return None


def find_frames(buf: bytearray, max_len: int = 512):
    """Remove and return complete frames while preserving an incomplete tail.

    ``parse_frame_at`` returns offsets relative to the current buffer.  Consume
    each complete frame immediately so those offsets can never become stale if
    the next candidate is incomplete.
    """
    frames = []
    while True:
        j = next_frame_pos(buf, -1)
        if j < 0:
            # Kein sicherer Frame-Anfang gefunden: nur kleines Resync-Fenster
            # behalten. A possible unit byte at the end must survive recv().
            keep_from = max(0, len(buf) - 32)
            if keep_from > 0:
                del buf[:keep_from]
            break

        parsed = parse_frame_at(buf, j, max_len)

        if parsed is INCOMPLETE:
            # TCP darf Modbus-Frames beliebig zerstueckeln.
            # Den gesamten angefangenen Frame behalten und beim naechsten recv()
            # fortsetzen. Nicht in eingebettete Marker wie "02 10 07 D1" resyncen.
            if j > 0:
                del buf[:j]
            break

        if parsed is None:
            # This marker cannot start a valid frame. Drop it and rescan the
            # remaining bytes, rather than retaining offsets into old data.
            del buf[:j + 1]
            continue

        frames.append(parsed)
        del buf[:parsed[8]]

    return frames


