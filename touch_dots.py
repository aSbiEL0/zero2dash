#!/usr/bin/env python3
import mmap
import struct
import select
from pathlib import Path
from PIL import Image, ImageDraw

FBDEV = "/dev/fb1"
TOUCH = "/dev/input/event0"
WIDTH = 320
HEIGHT = 240
DOT = 10

RAW_X_LEFT = 300
RAW_X_RIGHT = 3748
RAW_Y_TOP = 3880
RAW_Y_BOTTOM = 360


INPUT_EVENT = struct.Struct("llHHI")
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

ABS_X = 0x00
ABS_Y = 0x01
ABS_PRESSURE = 0x18
BTN_TOUCH = 0x14A


def scale(value, raw_min, raw_max, size):
    if raw_max == raw_min:
        return 0
    p = round((value - raw_min) * (size - 1) / (raw_max - raw_min))
    return max(0, min(size - 1, p))


def rgb565(image):
    r, g, b = image.split()
    r = r.point(lambda v: v >> 3).tobytes()
    g = g.point(lambda v: v >> 2).tobytes()
    b = b.point(lambda v: v >> 3).tobytes()
    out = bytearray()
    for i in range(len(r)):
        value = ((r[i] & 0x1F) << 11) | ((g[i] & 0x3F) << 5) | (b[i] & 0x1F)
        out += struct.pack("<H", value)
    return bytes(out)


def main():
    if not Path(FBDEV).exists():
        raise SystemExit(f"Missing framebuffer: {FBDEV}")
    if not Path(TOUCH).exists():
        raise SystemExit(f"Missing touch device: {TOUCH}")

    frame = Image.new("RGB", (WIDTH, HEIGHT), "white")
    dot = Image.new("RGB", (DOT, DOT), "white")
    ImageDraw.Draw(dot).ellipse((0, 0, DOT - 1, DOT - 1), fill="black")

    with open(FBDEV, "r+b", buffering=0) as fb:
        mm = mmap.mmap(fb.fileno(), WIDTH * HEIGHT * 2, mmap.MAP_SHARED, mmap.PROT_WRITE)
        mm.seek(0)
        mm.write(rgb565(frame))

        raw_x = 0
        raw_y = 0
        touching = False
        seen_x = False
        seen_y = False

        with open(TOUCH, "rb", buffering=0) as touch:
            try:
                while True:
                    ready, _, _ = select.select([touch], [], [], 0.2)
                    if not ready:
                        continue

                    raw = touch.read(INPUT_EVENT.size)
                    if len(raw) != INPUT_EVENT.size:
                        continue

                    _, _, ev_type, ev_code, ev_value = INPUT_EVENT.unpack(raw)

                    if ev_type == EV_KEY and ev_code == BTN_TOUCH:
                        touching = ev_value == 1
                        if not touching:
                            seen_x = False
                            seen_y = False

                    elif ev_type == EV_ABS:
                        if ev_code == ABS_X:
                            raw_x = ev_value
                            seen_x = True
                        elif ev_code == ABS_Y:
                            raw_y = ev_value
                            seen_y = True
                        elif ev_code == ABS_PRESSURE:
                            touching = ev_value > 0

                    elif ev_type == EV_SYN and touching and seen_x and seen_y:
                        x = scale(raw_y, RAW_X_LEFT, RAW_X_RIGHT, WIDTH)
                        y = scale(raw_x, RAW_Y_TOP, RAW_Y_BOTTOM, HEIGHT)

                        left = max(0, min(WIDTH - DOT, x - DOT // 2))
                        top = max(0, min(HEIGHT - DOT, y - DOT // 2))
                        frame.paste(dot, (left, top))

                        payload = rgb565(dot)
                        row_bytes = DOT * 2
                        for row in range(DOT):
                            start = row * row_bytes
                            offset = (((top + row) * WIDTH) + left) * 2
                            mm.seek(offset)
                            mm.write(payload[start:start + row_bytes])

                        seen_x = False
                        seen_y = False

            except KeyboardInterrupt:
                pass
            finally:
                mm.close()


if __name__ == "__main__":
    main()
