"""USB HID driver for the MAXSUN iCraft Z890 onboard LCD (0416:5021).

Protocol details: docs/protocol.md. Only the commands verified on hardware
are exposed here: 0x01 handshake, 0x0F clear overlay, 0x0E real-time JPG.
"""
import glob
import io
import os
import select
import struct
import time

from PIL import Image

VID_PID = "0416:5021"
WIDTH, HEIGHT = 412, 960
CMD_LEN, DATA_LEN = 64, 1024

CMD_HANDSHAKE = 0x01
CMD_BACKLIGHT = 0x0C
CMD_REALTIME_JPG = 0x0E
CMD_CLEAR_OVERLAY = 0x0F

# Handshake reply byte 20: the panel's display mode.
MODE_IDLE = 0x0A
MODE_REALTIME = 0x07


class DeviceNotFound(RuntimeError):
    pass


def find_nodes():
    """Return (cmd_node, data_node): the hidraw nodes of interface 0 and 1."""
    nodes = {}
    for h in glob.glob("/sys/class/hidraw/hidraw*"):
        dev = os.path.realpath(os.path.join(h, "device"))
        if VID_PID.upper() not in dev.upper():
            continue
        with open(os.path.join(dev, "..", "bInterfaceNumber")) as f:
            nodes[int(f.read(), 16)] = "/dev/" + os.path.basename(h)
    if set(nodes) != {0, 1}:
        raise DeviceNotFound(f"{VID_PID} not found or incomplete: {nodes}")
    return nodes[0], nodes[1]


def cmd_packet(cmd, payload=b""):
    return (bytes([cmd, 0x01, 0x00, 0x80]) + payload).ljust(CMD_LEN, b"\0")


def encode_jpg(img, quality=75):
    """Scale to the panel size (aspect ratio not kept, like the official app)."""
    buf = io.BytesIO()
    img.convert("RGB").resize((WIDTH, HEIGHT)).save(buf, "JPEG", quality=quality)
    return buf.getvalue()


class Lcd:
    def __init__(self):
        self.cmd_fd = self.data_fd = None

    def open(self):
        cmd_node, data_node = find_nodes()
        self.cmd_fd = os.open(cmd_node, os.O_RDWR)
        self.data_fd = os.open(data_node, os.O_RDWR)
        return self

    def close(self):
        for fd in (self.cmd_fd, self.data_fd):
            if fd is not None:
                os.close(fd)
        self.cmd_fd = self.data_fd = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    def _read_reply(self, timeout):
        r, _, _ = select.select([self.cmd_fd], [], [], timeout)
        return os.read(self.cmd_fd, CMD_LEN + 1) if r else None

    def command(self, cmd, payload=b"", timeout=1.0):
        os.write(self.cmd_fd, b"\0" + cmd_packet(cmd, payload))
        if not timeout:
            return None
        # Skip a stale reply left over from an earlier command.
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            reply = self._read_reply(left)
            if reply is None or reply[0] == cmd:
                return reply
        return None

    def handshake(self):
        """Returns the 64-byte status reply (byte 20: 0x0a idle, 0x07 real-time)."""
        return self.command(CMD_HANDSHAKE)

    def clear_overlay(self):
        """Removes the firmware's idle-mode 'Loading...' text."""
        self.command(CMD_CLEAR_OVERLAY)
        time.sleep(0.5)

    def set_backlight(self, level):
        """1-10; the firmware drives the PWM at level² percent and keeps the
        level in RAM only (no flash write), so it resets on power loss."""
        if not 1 <= level <= 10:
            raise ValueError(f"backlight level must be 1-10, got {level}")
        return self.command(CMD_BACKLIGHT, bytes([level]))

    def init(self):
        reply = self.handshake()
        self.clear_overlay()
        return reply

    def send_jpg(self, jpg):
        count = (len(jpg) + DATA_LEN - 1) // DATA_LEN
        header = struct.pack("<III", count, sum(jpg) & 0xFFFFFFFF, len(jpg))
        self.command(CMD_REALTIME_JPG, header, timeout=0)
        time.sleep(0.001)
        for i in range(count):
            chunk = jpg[i * DATA_LEN:(i + 1) * DATA_LEN].ljust(DATA_LEN, b"\0")
            os.write(self.data_fd, b"\0" + chunk)

    def show(self, img: Image.Image):
        self.send_jpg(encode_jpg(img))
