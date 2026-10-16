"""HID protocol for the ASUS ROG Pelta (A501) wireless headset.

Reverse engineered from ASUS AacAudioHal (C_A501_Protocol) and verified on hardware.
Every packet is a 64-byte output report with report ID 0xCC:

    0xCC, <group>, <cmd>, 0x00, 0x00, <data...>

Group 0x12 reads a value, 0x41 / 0x51 / 0x61 write one. The dongle answers each
packet with an input report that echoes group+cmd; read replies carry data at [5:].
"""

import glob
import os
import select
import time
from dataclasses import dataclass, field

VENDOR_ID = 0x0B05
PRODUCT_IDS = {0x1B84: "2.4 GHz dongle", 0x1B82: "USB-C cable"}
REPORT_ID = 0xCC
REPORT_LEN = 64

EFFECTS = {1: "Static", 2: "Breathing", 3: "Strobing", 4: "Color cycle"}
SLEEP_MINUTES = [2, 3, 5, 10, 15, 0]  # 0 = never
LOW_BATTERY_LEVELS = [0, 10, 20, 30, 40, 50]  # 0 = off
LATENCY = {0x28: "Low latency", 0x64: "Stable connection"}
VOICE_PROMPT = {1: "English", 2: "Chinese", 0: "Prompt sound"}
SIDETONE_MAX = 20


class PeltaError(Exception):
    pass


@dataclass
class Status:
    connected: bool = False
    battery: int | None = None
    charging: bool = False
    sleep_minutes: int = 5
    low_battery_level: int = 20
    low_battery_voice: bool = True
    effect: int = 4
    brightness: int = 50
    color: tuple = (128, 0, 255)
    sidetone: bool = False
    sidetone_level: int = 10
    noise_reduction: bool = False
    latency: int = 0x64
    voice_prompt: int = 1
    firmware: list = field(default_factory=list)


def find_hidraw():
    """Return (path, product_id) of the first Pelta hidraw node, or (None, None)."""
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(node, "device/uevent")) as f:
                uevent = f.read()
        except OSError:
            continue
        for line in uevent.splitlines():
            if line.startswith("HID_ID="):
                _, vid, pid = line[7:].split(":")
                vid, pid = int(vid, 16), int(pid, 16)
                if vid == VENDOR_ID and pid in PRODUCT_IDS:
                    return "/dev/" + os.path.basename(node), pid
    return None, None


class Pelta:
    def __init__(self, path=None):
        pid = None
        if path is None:
            path, pid = find_hidraw()
        if path is None:
            raise PeltaError("ROG Pelta dongle not found")
        self.path = path
        self.product_id = pid
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError:
            raise PeltaError(f"No permission for {path}. Install 70-rog-pelta.rules (see README).")

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- transport -------------------------------------------------------

    def _write(self, payload):
        pkt = bytes([REPORT_ID]) + bytes(payload)
        pkt += bytes(REPORT_LEN - len(pkt))
        try:
            os.write(self.fd, pkt)
        except OSError as e:
            raise PeltaError(f"Write failed: {e}") from e

    def _transact(self, payload, match, timeout=1.0):
        """Send payload and return the first input report starting with `match`."""
        self._drain()
        self._write(payload)
        end = time.monotonic() + timeout
        while (left := end - time.monotonic()) > 0:
            ready, _, _ = select.select([self.fd], [], [], left)
            if not ready:
                break
            try:
                report = os.read(self.fd, REPORT_LEN + 1)
            except BlockingIOError:
                continue
            if report[0] == REPORT_ID and report[1:1 + len(match)] == bytes(match):
                return report
        raise PeltaError(f"No reply to {bytes(payload[:2]).hex(' ')}")

    def _drain(self):
        while select.select([self.fd], [], [], 0)[0]:
            try:
                os.read(self.fd, REPORT_LEN + 1)
            except BlockingIOError:
                break

    def get(self, cmd, sub=b""):
        req = bytes([0x12, cmd]) + bytes(sub)
        return self._transact(req, req)[5:]

    def put(self, group, cmd, *data):
        self._transact(bytes([group, cmd, 0, 0, *data]), bytes([group, cmd]))

    # --- reads -----------------------------------------------------------

    def headset_connected(self):
        return self.get(0x00, b"\x00\x01")[0] == 1

    def power_info(self):
        sleep, battery, low_level, low_voice = self.get(0x07)[:4]
        if battery == 0xFE or battery > 100:
            battery = None
        return sleep, battery, low_level, bool(low_voice)

    def status(self):
        s = Status()
        s.connected = self.headset_connected()
        if not s.connected:
            return s
        s.sleep_minutes, s.battery, s.low_battery_level, s.low_battery_voice = self.power_info()
        s.charging = self.get(0x08)[0] == 1
        mode, bright, r, g, b = self.get(0x03)[:5]
        s.effect, s.brightness, s.color = mode, bright, (r, g, b)
        s.sidetone = self.get(0x24)[0] == 1
        s.sidetone_level = self.get(0x19)[0]
        s.noise_reduction = self._transact(b"\x41\x20", b"\x41\x20")[5] == 1
        s.latency = self.get(0x52)[0]
        s.voice_prompt = self.get(0x28)[0]
        fw = self.get(0x00, b"\x00\x00")[:8]
        s.firmware = [".".join(f"{x:02X}" for x in reversed(fw[i:i + 4])) for i in (0, 4)]
        return s

    # --- writes ----------------------------------------------------------

    def set_lighting(self, effect, brightness, color):
        """effect 1-4 (see EFFECTS), brightness 0-100 (0 = lights off), color (r, g, b)."""
        self.put(0x51, 0x10, 0)  # leave software (Aura Sync) mode so hardware effects run
        self.put(0x51, 0x28, effect, brightness, *color)

    def set_sidetone(self, on):
        self.put(0x41, 0x11, int(bool(on)))

    def set_sidetone_level(self, level):
        self.put(0x61, 0x11, max(0, min(SIDETONE_MAX, level)))

    def set_noise_reduction(self, on):
        self.put(0x41, 0x02, int(bool(on)))

    def set_latency(self, value):
        self.put(0x51, 0x52, value)

    def set_voice_prompt(self, value):
        self.put(0x41, 0x0A, value)

    def set_power(self, sleep_minutes, low_battery_level, low_battery_voice):
        self.put(0x51, 0x37, sleep_minutes, low_battery_level, int(bool(low_battery_voice)))
