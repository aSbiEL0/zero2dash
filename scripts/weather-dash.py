#!/usr/bin/env python3
"""Display the weather-dash background image on the framebuffer."""

import argparse
import mmap
import struct
import sys
from pathlib import Path

from PIL import Image

FBDEV_DEFAULT = "/dev/fb1"
W, H = 320, 240
DEFAULT_IMAGE = Path(__file__).resolve().parent.parent / "images" / "weather-dash-temp.png"


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Display weather-dash background image on TFT framebuffer.")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE), help=f"Background image path (default: {DEFAULT_IMAGE})")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
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

    write_to_framebuffer(frame, args.fbdev)
    print(f"Displayed weather-dash background on {args.fbdev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
