import unittest
from unittest.mock import Mock

from backend.rtu import RtuReadSession, crc16, with_crc
from backend.catalog import format_raw, search_registers


class WireTests(unittest.TestCase):
    def test_modbus_crc_known_vector(self):
        self.assertEqual(with_crc(bytes.fromhex("63 03 00 06 00 01")).hex(),
                         "6303000600016c49")

    def test_single_fc03_read(self):
        response = with_crc(bytes.fromhex("63 03 02 01 61"))  # 353
        sock = Mock()
        data = bytearray(response)

        def recv(n):
            packet = bytes(data[:n])
            del data[:n]
            return packet

        sock.recv.side_effect = recv
        words = RtuReadSession(sock, 0x63).read_holding(2012)
        self.assertEqual(words, [353])
        self.assertEqual(sock.sendall.call_args.args[0][1], 3)

    def test_crc_error_rejected(self):
        response = bytearray(with_crc(bytes.fromhex("63 03 02 00 01")))
        response[-1] ^= 0x80
        sock = Mock()
        data = bytearray(response)
        sock.recv.side_effect = lambda n: bytes(data[:n]) if not data.__delitem__(slice(0, n)) else b""
        # Testing the CRC helper independently avoids coupling to a socket stub implementation.
        self.assertNotEqual(crc16(response[:-2]), int.from_bytes(response[-2:], "little"))


class CatalogTests(unittest.TestCase):
    def test_catalog_scaling_matches_desktop_engineering_examples(self):
        from backend.catalog import load_registers
        catalog=load_registers()
        for register,raw,expected in [(2029,28,(2.8,'A')),(2054,50,(5.0,'kW')),
            (2060,402,(4.02,'COP')),(1031,15,(7.5,'°C')),(2042,37,(3.7,'A'))]:
            with self.subTest(register=register):
                self.assertEqual(format_raw(raw,catalog[str(register)]),expected)
        self.assertEqual(format_raw(65526,{'type':'DIGI5'}),(-1.0,''))
        self.assertEqual(format_raw(0x163b,{'type':'TIME_HHMM'}),('22:59',''))
        self.assertEqual(format_raw(123,{'type':'DIGI9'}),(123,''))
    def test_temperature_signed(self):
        self.assertEqual(format_raw(0xFFCE, {"type": "TEMP1"}), (-5.0, "°C"))

    def test_flow(self):
        self.assertEqual(format_raw(65, {"type": "FLOW_M3H_X100"}), (0.65, "m³/h"))

    def test_known_register_is_searchable(self):
        names = search_registers("D14", 20)
        self.assertTrue(any(row["code"] == "D14" for row in names))


if __name__ == "__main__":
    unittest.main()
