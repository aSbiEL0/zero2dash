#!/usr/bin/env python3
"""Display the pre-rendered weather image, refreshing it once if missing."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from PIL import Image

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framebuffer import write_framebuffer as write_rgb565_framebuffer

DEFAULT_IMAGE = MODULE_DIR / "weather.png"
DEFAULT_REFRESH_SCRIPT = MODULE_DIR / "weather_refresh.py"
FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
REFRESH_WAIT_SECS = 5.0
RESAMPLING_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def load_frame(image_path: Path, width: int, height: int) -> Image.Image:
    if not image_path.exists():
        raise FileNotFoundError(f"Weather image not found: {image_path}")
    return Image.open(image_path).convert("RGB").resize((width, height), RESAMPLING_LANCZOS)


def write_to_framebuffer(image: Image.Image, fbdev: str, width: int, height: int) -> None:
    write_rgb565_framebuffer(image, fbdev, width, height)


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
    parser = argparse.ArgumentParser(description="Display the pre-rendered weather image.")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE), help=f"Image path (default: {DEFAULT_IMAGE})")
    parser.add_argument("--refresh-script", default=str(DEFAULT_REFRESH_SCRIPT), help=f"Refresh script (default: {DEFAULT_REFRESH_SCRIPT})")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
    parser.add_argument("--refresh-wait", type=float, default=REFRESH_WAIT_SECS, help="Seconds to wait after a refresh attempt.")
    parser.add_argument("--output", help="Optional output image path for local verification (PNG/JPG).")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer write (useful for local testing).")
    parser.add_argument("--self-test", action="store_true", help="Run inline smoke tests and exit.")
    return parser.parse_args()


def run_self_tests() -> int:
    temp_dir = Path(os.getenv("TEMP", ".")).resolve()
    target = temp_dir / "weather-self-test.png"
    script = temp_dir / "weather-refresh-self-test.py"

    def successful_runner(_: Path) -> int:
        target.write_bytes(b"ok")
        return 0

    sleeps: list[float] = []
    result = ensure_image(target, script, 5.0, runner=successful_runner, sleeper=lambda value: sleeps.append(value))
    if not result or sleeps != [5.0]:
        raise AssertionError("ensure_image should retry once and accept the generated file")

    target.unlink(missing_ok=True)
    sleeps.clear()
    result = ensure_image(target, script, 5.0, runner=lambda _: 1, sleeper=lambda value: sleeps.append(value))
    if result or sleeps != [5.0]:
        raise AssertionError("ensure_image should fail gracefully after one retry")

    print("[weather/display.py] Self tests passed.")
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
        print(f"Weather image still unavailable after one refresh attempt: {image_path}", file=sys.stderr)
        return 1

    try:
        frame = load_frame(image_path, args.width, args.height)
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

    write_to_framebuffer(frame, args.fbdev, args.width, args.height)
    print(f"Displayed weather image on {args.fbdev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

