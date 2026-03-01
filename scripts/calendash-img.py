#!/usr/bin/env python3
"""Display a pre-rendered calendar image, then exit on touch or timeout."""

from __future__ import annotations

import argparse
import mmap
import select
import struct
import sys
import time
from pathlib import Path

from PIL import Image

FBDEV_DEFAULT = "/dev/fb1"
TOUCH_DEVICE_DEFAULT = "/dev/input/event0"
W, H = 320, 240
DEFAULT_IMAGE = Path(__file__).resolve().parent.parent / "images" / "calendash" / "output.jpg"
INPUT_EVENT_STRUCT = struct.Struct("llHHI")
EV_KEY = 0x01
BTN_TOUCH = 0x14A


def rgb888_to_rgb565(image: Image.Image) -> bytes:
    r, g, b = image.split()
    r = r.point(lambda value: value >> 3)
    g = g.point(lambda value: value >> 2)
    b = b.point(lambda value: value >> 3)

    rgb565 = bytearray()
    rp, gp, bp = r.tobytes(), g.tobytes(), b.tobytes()
    for i in range(len(rp)):
        value = ((rp[i] & 0x1F) << 11) | ((gp[i] & 0x3F) << 5) | (bp[i] & 0x1F)
        rgb565 += struct.pack("<H", value)
    return bytes(rgb565)


def load_frame(image_path: Path) -> Image.Image:
    if not image_path.exists():
        raise FileNotFoundError(f"Background image not found: {image_path}")
    return Image.open(image_path).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)


def write_to_framebuffer(image: Image.Image, fbdev: str) -> None:
    payload = rgb888_to_rgb565(image)
    with open(fbdev, "r+b", buffering=0) as framebuffer:
        mm = mmap.mmap(framebuffer.fileno(), W * H * 2, mmap.MAP_SHARED, mmap.PROT_WRITE)
        mm.seek(0)
        mm.write(payload)
        mm.close()


def wait_for_touch_or_timeout(device_path: Path, timeout_s: float) -> str:
    deadline = time.monotonic() + timeout_s

    if not device_path.exists():
        time.sleep(max(0.0, timeout_s))
        return "timeout"

    with open(device_path, "rb", buffering=0) as touch_dev:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "timeout"

            ready, _, _ = select.select([touch_dev], [], [], remaining)
            if not ready:
                return "timeout"

            payload = touch_dev.read(INPUT_EVENT_STRUCT.size)
            if len(payload) != INPUT_EVENT_STRUCT.size:
                return "timeout"

            _, _, event_type, code, value = INPUT_EVENT_STRUCT.unpack(payload)
            if event_type == EV_KEY and code == BTN_TOUCH and value == 1:
                return "touch"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Display calendash image then wait for touch/timeout.")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE), help=f"Image path (default: {DEFAULT_IMAGE})")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument(
        "--touch-device",
        default=TOUCH_DEVICE_DEFAULT,
        help=f"Touch input device path (default: {TOUCH_DEVICE_DEFAULT})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds to wait before exiting (default: 30)",
    )
    parser.add_argument("--output", help="Optional output image path for local verification (PNG/JPG)")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer write (useful for local testing).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        frame = load_frame(Path(args.image))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.output:
        frame.save(args.output)
        print(f"Saved preview image to {args.output}")

    if args.no_framebuffer:
        print("Skipping framebuffer write (--no-framebuffer set)")
        return 0

    fb_path = Path(args.fbdev)
    if not fb_path.exists():
        print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
        return 1

    if args.timeout < 0:
        print("Timeout cannot be negative.", file=sys.stderr)
        return 1

    write_to_framebuffer(frame, args.fbdev)
    print(f"Displayed calendash image on {args.fbdev}")

    trigger = wait_for_touch_or_timeout(Path(args.touch_device), args.timeout)
    print(f"Exiting calendash image script ({trigger})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
