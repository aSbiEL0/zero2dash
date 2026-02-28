#!/usr/bin/env python3
"""Placeholder display test: draw black screen with bold white TEST text."""

import argparse
import mmap
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FBDEV_DEFAULT = "/dev/fb1"
W, H = 320, 240


def load_font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for font_path in candidates:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_test_frame() -> Image.Image:
    image = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = load_font(96, bold=True)

    text = "TEST"
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    text_w = x1 - x0
    text_h = y1 - y0

    x = (W - text_w) // 2
    y = (H - text_h) // 2
    draw.text((x, y), text, font=font, fill=(255, 255, 255))

    return image


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


def write_to_framebuffer(image: Image.Image, fbdev: str) -> None:
    payload = rgb888_to_rgb565(image)
    with open(fbdev, "r+b", buffering=0) as framebuffer:
        mm = mmap.mmap(framebuffer.fileno(), W * H * 2, mmap.MAP_SHARED, mmap.PROT_WRITE)
        mm.seek(0)
        mm.write(payload)
        mm.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Display a TEST placeholder on the TFT framebuffer.")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--output", help="Optional output image path for local verification (PNG/JPG)")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer write (useful for local testing).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    frame = make_test_frame()

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
    print(f"Displayed TEST placeholder on {args.fbdev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
