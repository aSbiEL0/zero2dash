#!/usr/bin/env python3
"""Display a pre-rendered calendar image, then exit on touch or timeout."""

from __future__ import annotations

import argparse
import mmap
import os
import select
import struct
import sys
import time
from pathlib import Path

from PIL import Image

FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
TOUCH_DEVICE_DEFAULT = os.environ.get("TOUCH_DEVICE", "/dev/input/event0")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
DEFAULT_IMAGE = Path(__file__).resolve().parent.parent / "images" / "calendash" / "output.png"
INPUT_EVENT_STRUCT = struct.Struct("llHHI")
EV_KEY = 0x01
BTN_TOUCH = 0x14A
RESAMPLING_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


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


def load_frame(image_path: Path, width: int, height: int) -> Image.Image:
    if not image_path.exists():
        raise FileNotFoundError(f"Background image not found: {image_path}")
    return Image.open(image_path).convert("RGB").resize((width, height), RESAMPLING_LANCZOS)


def write_to_framebuffer(image: Image.Image, fbdev: str, width: int, height: int) -> None:
    payload = rgb888_to_rgb565(image)
    expected = width * height * 2
    if len(payload) != expected:
        raise RuntimeError(f"Framebuffer payload size mismatch: expected {expected} bytes, got {len(payload)} bytes")

    with open(fbdev, "r+b", buffering=0) as framebuffer:
        mm = mmap.mmap(framebuffer.fileno(), expected, mmap.MAP_SHARED, mmap.PROT_WRITE)
        mm.seek(0)
        mm.write(payload)
        mm.close()


def wait_for_touch_or_timeout(device_path: Path, timeout_s: float) -> str:
    deadline = time.monotonic() + timeout_s

    if not device_path.exists():
        time.sleep(max(0.0, timeout_s))
        return "timeout"

    fd = os.open(device_path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        pending = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "timeout"

            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                return "timeout"

            chunk = os.read(fd, 4096)
            if not chunk:
                continue

            pending.extend(chunk)
            while len(pending) >= INPUT_EVENT_STRUCT.size:
                payload = bytes(pending[: INPUT_EVENT_STRUCT.size])
                del pending[: INPUT_EVENT_STRUCT.size]
                _, _, event_type, code, value = INPUT_EVENT_STRUCT.unpack(payload)
                if event_type == EV_KEY and code == BTN_TOUCH and value == 1:
                    return "touch"
    finally:
        os.close(fd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Display calendash image then wait for touch/timeout.")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE), help=f"Image path (default: {DEFAULT_IMAGE})")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
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
        frame = load_frame(Path(args.image), args.width, args.height)
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

    if args.width <= 0 or args.height <= 0:
        print("Width/height must be positive integers.", file=sys.stderr)
        return 1

    write_to_framebuffer(frame, args.fbdev, args.width, args.height)
    print(f"Displayed calendash image on {args.fbdev}")

    trigger = wait_for_touch_or_timeout(Path(args.touch_device), args.timeout)
    print(f"Exiting calendash image script ({trigger})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
