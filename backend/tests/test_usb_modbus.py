"""Exercise the selected physical link without opening any real device."""

import os
from pathlib import Path
import re
import select
from tempfile import TemporaryDirectory
import threading
from unittest import TestCase, skipUnless
from unittest.mock import patch

from backend import settings
from backend.bus_connection import BusConnectionManager
from backend.bus_stream import connect_bus
from backend.display_bus import DisplayBus
from backend.display_protocol import DisplayProtocol
from backend.rtu import StandardConnection, with_crc
from backend.tests.test_display_bus import packet


class UsbConfigurationTests(TestCase):
    def test_defaults_and_tcp_to_usb_round_trip_for_each_bus(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.multiple(
                settings, STATE_DIR=root, WARMLINK_FILE=root / "warmlink.json"
            ):
                for i, (kind, baudrate) in enumerate(settings.SERIAL_BAUDRATES.items()):
                    with self.subTest(kind=kind):

                        def save(**kwargs):
                            return (
                                settings.save_warmlink(**kwargs)
                                if kind == "warmlink_raw"
                                else settings.save_local_bus(kind, **kwargs)
                            )

                        endpoint = (
                            settings.warmlink_endpoint
                            if kind == "warmlink_raw"
                            else lambda: settings.local_endpoint(kind)
                        )
                        save(host="192.168.100.10", port=2001 + i, enabled=True)
                        self.assertEqual(endpoint().medium, "tcp")
                        row = save(
                            host="192.168.100.10",
                            port=2001 + i,
                            enabled=True,
                            medium="serial",
                            serial_device=f"/dev/ttyUSB{i}",
                        )
                        self.assertEqual(
                            (row["baudrate"], endpoint().baudrate), (baudrate, baudrate)
                        )
                        self.assertEqual(endpoint().serial_device, f"/dev/ttyUSB{i}")
                        with self.assertRaises(ValueError):
                            save(
                                host="",
                                port=2001,
                                enabled=True,
                                medium="serial",
                                serial_device="/dev/null",
                            )
                with self.assertRaisesRegex(ValueError, "bereits"):
                    settings.save_warmlink(
                        "", 2001, True, medium="serial", serial_device="/dev/ttyUSB0"
                    )


@skipUnless(os.name == "posix", "Pseudo-terminal test runs in Linux CI")
class SerialProtocolTests(TestCase):
    def setUp(self):
        import pty

        master, device = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, device)
        self.master = master
        self.path = os.ttyname(device)
        patches = (
            patch("backend.bus_stream.SERIAL_DEVICE", re.compile(re.escape(self.path))),
            patch("backend.transport_selection.stored", return_value=None),
        )
        for change in patches:
            change.start()
            self.addCleanup(change.stop)

    def endpoint(self, speed, unit=99):
        return settings.Endpoint("", 0, unit, 0.4, "serial", self.path, speed)

    def test_standard_modbus_reads_through_a_real_serial_stream(self):
        def reply():
            if select.select([self.master], [], [], 1)[0]:
                request = os.read(self.master, 8)
                if request == with_crc(bytes((99, 3, 3, 233, 0, 1))):
                    os.write(self.master, with_crc(bytes((99, 3, 2, 0, 42))))

        standard = StandardConnection()
        self.addCleanup(standard.disconnect)
        with standard.session(self.endpoint(9600)) as session:
            thread = threading.Thread(target=reply, daemon=True)
            thread.start()
            self.assertEqual(session.read_holding(1001), [42])
            thread.join(1)

    def test_lte_passive_parser_reads_serial_traffic(self):
        endpoint = self.endpoint(9600)
        bus = BusConnectionManager()
        observed = []
        with connect_bus(endpoint, transport="display") as stream:
            from backend.warmlink_protocol import WarmlinkSession

            session = WarmlinkSession(
                stream, endpoint, on_observed_read=lambda a, v: observed.append((a, v))
            )
            os.write(
                self.master,
                with_crc(bytes((99, 3, 3, 233, 0, 1)))
                + with_crc(bytes((99, 3, 2, 0, 42))),
            )
            for _ in range(8):
                session.receive(0.075)
                if observed:
                    break
            self.assertEqual(observed, [(1001, [42])])
        with bus.open(endpoint) as client:
            self.assertEqual(client.sock.port.baudrate, 9600)

    def test_display_serial_stream_keeps_passive_protocol(self):
        bus = DisplayBus()
        observed = []
        with bus.connect(self.endpoint(4800, 3)) as stream:
            protocol = DisplayProtocol(lambda address, words: observed.append(address))
            os.write(self.master, packet(2001, unit=0))
            for _ in range(8):
                protocol.feed(stream.recv(4096))
                if observed:
                    break
            self.assertEqual(observed, [2001])
            self.assertIsNone(protocol.tick())
            self.assertEqual(stream.port.baudrate, 4800)
