#!/usr/bin/env python3
"""Standalone framebuffer blackout animation with a bouncing PNG icon."""

from __future__ import annotations

import argparse
import mmap
import os
import signal
import struct
import sys
import time
from pathlib import Path

from PIL import Image

FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
FPS_DEFAULT = 20.0
ICON_DEFAULT = Path(__file__).resolve().parent.parent / "images" / "raspberry-pi-icon.png"
ICON_SIZE_RATIO = 0.18
ICON_MIN_SIZE = 28
ICON_MAX_SIZE = 72
STEP_X = 2
STEP_Y = 2
RESAMPLING_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
_STOP_REQUESTED = False


def request_stop(_signum: int, _frame: object) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a black screen with a bouncing PNG icon.")
    parser.add_argument("--icon", default=str(ICON_DEFAULT), help=f"PNG icon path (default: {ICON_DEFAULT})")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
    parser.add_argument("--fps", type=float, default=FPS_DEFAULT, help=f"Animation frame rate (default: {FPS_DEFAULT})")
    parser.add_argument("--output", help="Optional output PNG path for preview frames.")
    parser.add_argument(
        "--no-framebuffer",
        action="store_true",
        help="Skip framebuffer writes. With --output, render one frame and exit.",
    )
    return parser.parse_args()


def rgb888_to_rgb565(image: Image.Image) -> bytes:
    r, g, b = image.split()
    r = r.point(lambda value: value >> 3)
    g = g.point(lambda value: value >> 2)
    b = b.point(lambda value: value >> 3)

    rgb565 = bytearray()
    rp, gp, bp = r.tobytes(), g.tobytes(), b.tobytes()
    for idx in range(len(rp)):
        value = ((rp[idx] & 0x1F) << 11) | ((gp[idx] & 0x3F) << 5) | (bp[idx] & 0x1F)
        rgb565 += struct.pack("<H", value)
    return bytes(rgb565)


class FramebufferWriter:
    def __init__(self, fbdev: str, width: int, height: int) -> None:
        self.fbdev = fbdev
        self.width = width
        self.height = height
        self.expected = width * height * 2
        self._handle = None
        self._mapping = None

    def open(self) -> None:
        handle = open(self.fbdev, "r+b", buffering=0)
        mapping = mmap.mmap(handle.fileno(), self.expected, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self._handle = handle
        self._mapping = mapping

    def write(self, image: Image.Image) -> None:
        if self._mapping is None:
            raise RuntimeError("Framebuffer is not open")

        payload = rgb888_to_rgb565(image)
        if len(payload) != self.expected:
            raise RuntimeError(
                f"Framebuffer payload size mismatch: expected {self.expected} bytes, got {len(payload)} bytes"
            )

        self._mapping.seek(0)
        self._mapping.write(payload)

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "FramebufferWriter":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def _alpha_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return image.getchannel("A").getbbox()


def normalise_icon(icon: Image.Image) -> Image.Image:
    rgba = icon.convert("RGBA")
    bbox = _alpha_bbox(rgba)
    if bbox is None:
        raise ValueError("Icon contains no visible pixels")

    trimmed = rgba.crop(bbox)
    alpha = trimmed.getchannel("A")
    weighted_luma = 0.0
    weighted_alpha = 0.0
    for red, green, blue, alpha_value in trimmed.getdata():
        if alpha_value == 0:
            continue
        luma = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        weighted_luma += luma * alpha_value
        weighted_alpha += alpha_value

    if weighted_alpha == 0:
        raise ValueError("Icon alpha channel is empty")

    average_luma = weighted_luma / weighted_alpha
    if average_luma < 48:
        visible = Image.new("RGBA", trimmed.size, (255, 255, 255, 0))
        visible.putalpha(alpha)
        return visible
    return trimmed


def resize_icon(icon: Image.Image, width: int, height: int) -> Image.Image:
    target = int(min(width, height) * ICON_SIZE_RATIO)
    target = max(ICON_MIN_SIZE, min(ICON_MAX_SIZE, target))
    resized = icon.copy()
    resized.thumbnail((target, target), RESAMPLING_LANCZOS)
    return resized


def render_frame(width: int, height: int, icon: Image.Image, x: int, y: int) -> Image.Image:
    frame = Image.new("RGB", (width, height), (0, 0, 0))
    frame.paste(icon, (x, y), icon)
    return frame


def advance_position(
    x: int,
    y: int,
    vx: int,
    vy: int,
    width: int,
    height: int,
    icon_width: int,
    icon_height: int,
) -> tuple[int, int, int, int]:
    next_x = x + vx
    next_y = y + vy
    max_x = max(0, width - icon_width)
    max_y = max(0, height - icon_height)

    if next_x <= 0:
        next_x = 0
        vx = abs(vx)
    elif next_x >= max_x:
        next_x = max_x
        vx = -abs(vx)

    if next_y <= 0:
        next_y = 0
        vy = abs(vy)
    elif next_y >= max_y:
        next_y = max_y
        vy = -abs(vy)

    return next_x, next_y, vx, vy


def validate_args(args: argparse.Namespace) -> int | None:
    if args.width <= 0 or args.height <= 0:
        print("Width/height must be positive integers.", file=sys.stderr)
        return 1
    if args.fps <= 0:
        print("FPS must be a positive number.", file=sys.stderr)
        return 1
    return None


def main() -> int:
    args = parse_args()
    validation_error = validate_args(args)
    if validation_error is not None:
        return validation_error

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    icon_path = Path(args.icon)
    if not icon_path.exists():
        print(f"Icon not found: {icon_path}", file=sys.stderr)
        return 1

    try:
        with Image.open(icon_path) as raw_icon:
            icon = resize_icon(normalise_icon(raw_icon), args.width, args.height)
    except Exception as exc:
        print(f"Unable to load icon {icon_path}: {exc}", file=sys.stderr)
        return 1

    icon_width, icon_height = icon.size
    x = 0
    y = 0
    vx = STEP_X
    vy = STEP_Y
    frame_interval = 1.0 / args.fps

    if not args.no_framebuffer:
        fb_path = Path(args.fbdev)
        if not fb_path.exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1

    preview_written = False

    if args.no_framebuffer:
        while not _STOP_REQUESTED:
            frame = render_frame(args.width, args.height, icon, x, y)
            if args.output and not preview_written:
                frame.save(args.output)
                print(f"Saved preview image to {args.output}")
                return 0

            x, y, vx, vy = advance_position(x, y, vx, vy, args.width, args.height, icon_width, icon_height)
            time.sleep(frame_interval)
        return 0

    try:
        with FramebufferWriter(args.fbdev, args.width, args.height) as framebuffer:
            while not _STOP_REQUESTED:
                started = time.monotonic()
                frame = render_frame(args.width, args.height, icon, x, y)
                framebuffer.write(frame)

                if args.output and not preview_written:
                    frame.save(args.output)
                    print(f"Saved preview image to {args.output}")
                    preview_written = True

                x, y, vx, vy = advance_position(x, y, vx, vy, args.width, args.height, icon_width, icon_height)
                remaining = frame_interval - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)
    except Exception as exc:
        print(f"Blackout animation failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
