#!/usr/bin/env python3
"""Display the pre-rendered currency image, refreshing it once if missing."""

from __future__ import annotations

import argparse
import mmap
import os
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_IMAGE = MODULE_DIR / "current-currency.png"
DEFAULT_REFRESH_SCRIPT = MODULE_DIR / "currency-rate.py"
FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
REFRESH_WAIT_SECS = 30.0


def rgb888_to_rgb565(image: Any) -> bytes:
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


def load_frame(image_path: Path, width: int, height: int) -> Any:
    from PIL import Image

    resampling_lanczos = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    if not image_path.exists():
        raise FileNotFoundError(f"Currency image not found: {image_path}")
    return Image.open(image_path).convert("RGB").resize((width, height), resampling_lanczos)


def write_to_framebuffer(image: Any, fbdev: str, width: int, height: int) -> None:
    payload = rgb888_to_rgb565(image)
    expected = width * height * 2
    if len(payload) != expected:
        raise RuntimeError(f"Framebuffer payload size mismatch: expected {expected} bytes, got {len(payload)} bytes")

    with open(fbdev, "r+b", buffering=0) as framebuffer:
        mm = mmap.mmap(framebuffer.fileno(), expected, mmap.MAP_SHARED, mmap.PROT_WRITE)
        mm.seek(0)
        mm.write(payload)
        mm.close()


def refresh_image(refresh_script: Path) -> int:
    completed = subprocess.run([sys.executable, "-u", str(refresh_script)], check=False)
    return completed.returncode


def ensure_image(
    image_path: Path,
    refresh_script: Path,
    wait_secs: float,
    *,
    runner: Callable[[Path], int] = refresh_image,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    if image_path.exists():
        return True

    runner(refresh_script)
    sleeper(wait_secs)
    return image_path.exists()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Display the GBP/PLN currency image.")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE), help=f"Image path (default: {DEFAULT_IMAGE})")
    parser.add_argument("--refresh-script", default=str(DEFAULT_REFRESH_SCRIPT), help=f"Refresh script (default: {DEFAULT_REFRESH_SCRIPT})")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
    parser.add_argument("--refresh-wait", type=float, default=REFRESH_WAIT_SECS, help="Seconds to wait after the refresh attempt.")
    parser.add_argument("--output", help="Optional output image path for local verification (PNG/JPG).")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer write (useful for local testing).")
    parser.add_argument("--self-test", action="store_true", help="Run inline smoke tests and exit.")
    return parser.parse_args()


def run_self_tests() -> int:
    temp_dir = Path(os.getenv("TEMP", ".")).resolve()
    target = temp_dir / "currency-self-test.png"
    script = temp_dir / "currency-rate-self-test.py"

    def successful_runner(_: Path) -> int:
        target.write_bytes(b"ok")
        return 0

    sleeps: list[float] = []
    result = ensure_image(target, script, 30.0, runner=successful_runner, sleeper=lambda value: sleeps.append(value))
    if not result or sleeps != [30.0]:
        raise AssertionError("ensure_image should retry once and accept the generated file")

    target.unlink(missing_ok=True)
    sleeps.clear()
    result = ensure_image(target, script, 30.0, runner=lambda _: 1, sleeper=lambda value: sleeps.append(value))
    if result or sleeps != [30.0]:
        raise AssertionError("ensure_image should fail gracefully after one retry")

    print("[currency.py] Self tests passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_tests()

    image_path = Path(args.image)
    refresh_script = Path(args.refresh_script)

    if args.width <= 0 or args.height <= 0:
        print("Width/height must be positive integers.", file=sys.stderr)
        return 1

    if args.refresh_wait < 0:
        print("Refresh wait cannot be negative.", file=sys.stderr)
        return 1

    if not ensure_image(image_path, refresh_script, args.refresh_wait):
        print(f"Currency image still unavailable after one refresh attempt: {image_path}")
        return 0

    try:
        frame = load_frame(image_path, args.width, args.height)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 0

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

    write_to_framebuffer(frame, args.fbdev, args.width, args.height)
    print(f"Displayed currency image on {args.fbdev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



