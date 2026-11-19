"""Passive HMI decoding and the sole allowed two-stage snapshot command.

Reviewed against FoxAir_Control a98b16c: core/display_protocol.py and the
ACK-driven _display_fake_reboot_* controller. No generic write API exists.
"""

import re
import time
from backend.warmlink_frames import find_frames, next_frame_pos
from backend.rtu import with_crc

REQUIRED = (1001, 1091, 1181, 1271, 1361, 1451)
OPTIONAL = (1541,)


def valid_packet(start, words):
    if len(words) != 90 or words[8] != 0x0210 or words[9] != start:
        return False
    identity = b"".join(n.to_bytes(2, "big") for n in words[:6])
    return re.fullmatch(rb"WF[0-9]{10}", identity) is not None


class DisplayProtocol:
    def __init__(self, on_words, clock=time.monotonic):
        self.on_words, self.clock = on_words, clock
        self.buffer = bytearray()
        self.last_rx = clock()
        self.pending = {}
        self.seen = {}
        self.sync = {
            "status": "idle",
            "completed": 0,
            "total": 6,
            "error": None,
            "phase": "idle",
        }
        self.phase = "idle"
        self.deadline = 0
        self.retries = 0
        self.attempt = 0
        self.since = None
        self.last_success = -100
        self.flag = None
        self.flag_time = -100

    def start(self):
        now = self.clock()
        if self.sync["status"] == "running":
            return dict(self.sync)
        if now - self.last_success < 8:
            return dict(self.sync)
        self.sync = {
            "status": "running",
            "completed": 0,
            "total": 6,
            "error": None,
            "phase": "prepare",
        }
        self.attempt = 1
        self.retries = 0
        self.since = None
        self.phase = "send_prepare"
        self.deadline = now + 8
        return dict(self.sync)

    def _finish(self):
        received = [
            start
            for start in REQUIRED
            if self.since is not None and self.seen.get(start, -1) >= self.since
        ]
        self.sync["completed"] = len(received)
        self.sync["received"] = received
        self.sync["missing"] = [start for start in REQUIRED if start not in received]
        if len(received) == 6:
            self.sync.update(status="complete", error=None, phase="complete")
            self.phase = "idle"
            self.last_success = self.clock()
            return True
        return False

    def feed(self, data):
        now = self.clock()
        self.last_rx = now
        self.buffer.extend(data)
        frames = find_frames(self.buffer, 125)
        if len(self.buffer) > 4096:
            raise ValueError("Display-Stream nicht synchronisiert")
        for frame in frames:
            slave, fc, start, count, payload, _, raw, _, _, kind = frame
            if kind == "read-request":
                old = self.pending.get(slave)
                ambiguous = old is not None and now - old[2] < 2
                self.pending[slave] = (start, count, now, ambiguous)
            elif kind == "read-response":
                pending = self.pending.pop(slave, None)
                if (
                    pending
                    and not pending[3]
                    and now - pending[2] <= 2
                    and count == pending[1] * 2
                ):
                    words = [
                        int.from_bytes(payload[i : i + 2], "big")
                        for i in range(0, len(payload), 2)
                    ]
                    if slave == 3 and pending[:2] == (3001, 21):
                        self.flag = words[10]
                        self.flag_time = now
                        if self.phase == "wait_flag" and self.flag == 0x8000:
                            self.phase = "upload"
                            self.deadline = now + 14
                    elif slave == 1 and pending[:2] == (2099, 51):
                        self.on_words(91099, words)
            elif kind == "word-frame":
                words = [
                    int.from_bytes(payload[i : i + 2], "big")
                    for i in range(1, len(payload), 2)
                ]
                allowed = (slave == 3 and start in REQUIRED + OPTIONAL) or (
                    slave == 0 and start in (2001, 2091)
                )
                if allowed and valid_packet(start, words):
                    self.on_words(start, words)
                    if slave == 3:
                        self.seen[start] = now
                    if self.sync["status"] == "running":
                        self._finish()
            elif kind == "write-response" and slave == 3 and count == 1:
                if start == 0x5112 and self.phase == "wait_prepare":
                    self.phase = "send_flag"
                    self.retries = 0
                    self.deadline = now + 8
                    self.not_before = now + 0.35
                elif start == 0x0BC3 and self.phase == "wait_flag":
                    self.phase = "upload"
                    self.deadline = now + 14
        return len(frames)

    def tick(self):
        """Return only a fixed snapshot command, or no transmission at all."""
        if self.sync["status"] != "running":
            return None
        now = self.clock()
        if self.since is not None and self._finish():
            return None
        self.sync["phase"] = self.phase
        if self.phase in ("send_prepare", "send_flag"):
            if now > self.deadline:
                self.sync.update(
                    status="partial" if self.sync["completed"] else "error",
                    error="Display-Bus belegt; kein sicherer Sendezeitpunkt",
                    phase="error",
                )
                self.phase = "idle"
                return None
            if (
                now - self.last_rx >= 0.05
                and self.buffer
                and next_frame_pos(self.buffer, -1) < 0
            ):
                self.buffer.clear()
            if (
                now - self.last_rx < 0.05
                or self.buffer
                or now < getattr(self, "not_before", 0)
            ):
                return None
            if any(now - p[2] < 2 for p in self.pending.values()):
                return None
            prepare = self.phase == "send_prepare"
            address, value = (0x5112, 0) if prepare else (0x0BC3, 0x8000)
            self.phase = "wait_prepare" if prepare else "wait_flag"
            self.deadline = now + (1.6 if prepare else 1.7)
            self.retries += 1
            if not prepare and self.since is None:
                self.since = now
            return with_crc(
                bytes((3, 16))
                + address.to_bytes(2, "big")
                + b"\x00\x01\x02"
                + value.to_bytes(2, "big")
            )
        if now < self.deadline:
            return None
        if self.phase == "upload":
            self.attempt += 1
            self.retries = 0
            if self.attempt > 3:
                self._finish()
                self.sync.update(
                    status="partial" if self.sync["completed"] else "error",
                    error="Display-Upload unvollständig; fehlende Pflichtpakete",
                    phase="error",
                )
                self.phase = "idle"
                return None
            self.phase = "send_prepare"
            self.deadline = now + 8
        elif self.retries < (3 if self.phase == "wait_prepare" else 4):
            self.phase = "send_prepare" if self.phase == "wait_prepare" else "send_flag"
            self.deadline = now + 8
        else:
            self.attempt += 1
            self.retries = 0
            if self.attempt > 3:
                self.sync.update(
                    status="partial" if self.sync["completed"] else "error",
                    error="Display-Trigger nicht bestätigt",
                    phase="error",
                )
                self.phase = "idle"
            else:
                self.phase = "send_prepare"
                self.deadline = now + 8
        return None
