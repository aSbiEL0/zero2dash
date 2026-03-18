#!/usr/bin/env python3
"""Standalone framebuffer blackout animation with a bouncing PNG icon."""

from __future__ import annotations

import argparse
import glob
import os
import queue
import re
import select
import signal
import subprocess
import struct
import sys
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from framebuffer import FramebufferWriter

FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
FPS_DEFAULT = 40.0
ICON_DEFAULT = Path(__file__).resolve().parent / "raspberry-pi-icon.png"
ICON_SIZE_RATIO = 0.18
ICON_MIN_SIZE = 28
ICON_MAX_SIZE = 72
STEP_X = 1
STEP_Y = 1
TIME_OVERLAY_SECS = float(os.environ.get("BLACKOUT_TIME_OVERLAY_SECS", "3.0"))
HOLD_TO_SELECTOR_SECS = float(os.environ.get("BLACKOUT_HOLD_TO_SELECTOR_SECS", "3.0"))
TIME_TEXT_RGB = (64, 64, 64)
RESAMPLING_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
_STOP_REQUESTED = False
BASE_DIR = Path(__file__).resolve().parents[2]
BOOT_SELECTOR_SCRIPT = BASE_DIR / "boot" / "boot_selector.py"
BOOT_SELECTOR_SERVICE = os.environ.get("BLACKOUT_BOOT_SELECTOR_SERVICE", "boot-selector.service").strip() or "boot-selector.service"

# linux/input-event-codes.h
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03
ABS_X = 0x00
ABS_MT_POSITION_X = 0x35
ABS_MT_TRACKING_ID = 0x39
BTN_TOUCH = 0x14A
INPUT_EVENT_STRUCT = struct.Struct("llHHI")

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
)


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


def _read_sysfs_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _capability_mask(event_path: str, capability: str) -> int:
    raw = _read_sysfs_text(Path("/sys/class/input") / Path(event_path).name / "device" / "capabilities" / capability)
    if not raw:
        return 0
    try:
        return int(raw, 16)
    except ValueError:
        return 0


def _touch_candidate_details(event_path: str) -> tuple[tuple[int, int, int, int], str]:
    base = Path("/sys/class/input") / Path(event_path).name / "device"
    name = _read_sysfs_text(base / "name")
    name_lc = name.lower()
    abs_mask = _capability_mask(event_path, "abs")
    key_mask = _capability_mask(event_path, "key")

    has_abs_x = bool(abs_mask & (1 << ABS_X))
    has_abs_mt_x = bool(abs_mask & (1 << ABS_MT_POSITION_X))
    has_touch_abs = has_abs_x or has_abs_mt_x
    has_btn_touch = bool(key_mask & (1 << BTN_TOUCH))

    name_bonus = 0
    if "touchscreen" in name_lc:
        name_bonus = 5
    elif "touch" in name_lc:
        name_bonus = 3
    elif "mouse" in name_lc or "keyboard" in name_lc:
        name_bonus = -3

    score = (7 if has_touch_abs else -7) + (5 if has_btn_touch else -1) + name_bonus
    match = re.search(r"event(\d+)$", event_path)
    index = int(match.group(1)) if match else 999
    reason = (
        f"score={score}; name='{name or 'unknown'}'; "
        f"touch_abs={'yes' if has_touch_abs else 'no'}; BTN_TOUCH={'yes' if has_btn_touch else 'no'}"
    )
    return (score, int(has_touch_abs), int(has_btn_touch), -index), reason


def select_touch_device() -> str | None:
    forced = os.environ.get("TOUCH_DEVICE", "").strip() or os.environ.get("BLACKOUT_TOUCH_DEVICE", "").strip()
    if forced:
        resolved = forced
        if forced.startswith("event") and forced[5:].isdigit():
            resolved = f"/dev/input/{forced}"
        if Path(resolved).exists():
            print(f"[blackout] Touch device selected: {resolved} (forced)", flush=True)
            return resolved
        print(f"[blackout] Touch override not found: {forced}", flush=True)

    candidates = sorted(glob.glob("/dev/input/event*"))
    if not candidates:
        print("[blackout] No /dev/input/event* devices found; touch disabled.", flush=True)
        return None

    ranked: list[tuple[tuple[int, int, int, int], str, str]] = []
    for path in candidates:
        rank, reason = _touch_candidate_details(path)
        ranked.append((rank, path, reason))
    ranked.sort(reverse=True)

    best_rank, best_path, best_reason = ranked[0]
    if best_rank[0] <= 0:
        print(f"[blackout] No suitable touch device found; touch disabled. Reason: {best_reason}", flush=True)
        return None

    print(f"[blackout] Touch device selected: {best_path} ({best_reason})", flush=True)
    return best_path

def touch_worker(event_q: "queue.Queue[str]", stop_evt: threading.Event) -> None:
    device = select_touch_device()
    if not device:
        return

    touch_down = False
    touch_started_at = 0.0

    def emit_touch_event() -> None:
        duration = time.monotonic() - touch_started_at
        event_q.put("hold" if duration >= HOLD_TO_SELECTOR_SECS else "tap")

    try:
        with open(device, "rb", buffering=0) as fd:
            while not stop_evt.is_set():
                readable, _, _ = select.select([fd], [], [], 0.2)
                if not readable:
                    continue

                raw = fd.read(INPUT_EVENT_STRUCT.size)
                if len(raw) != INPUT_EVENT_STRUCT.size:
                    continue

                _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)
                if ev_type == EV_KEY and ev_code == BTN_TOUCH:
                    if ev_value == 1:
                        touch_down = True
                        touch_started_at = time.monotonic()
                    elif ev_value == 0 and touch_down:
                        touch_down = False
                        emit_touch_event()
                elif ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
                    if ev_value == -1 and touch_down:
                        touch_down = False
                        emit_touch_event()
                    elif ev_value >= 0:
                        touch_down = True
                        touch_started_at = time.monotonic()
                elif ev_type in (EV_ABS, EV_SYN):
                    continue
    except Exception as exc:
        print(f"[blackout] Touch worker stopped ({device}): {exc}", flush=True)


def activate_boot_selector() -> int:
    global _STOP_REQUESTED

    running_under_systemd = bool(os.environ.get("INVOCATION_ID", "").strip())
    if running_under_systemd:
        result = subprocess.run(["systemctl", "start", BOOT_SELECTOR_SERVICE], check=False, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[blackout] Long press detected; started {BOOT_SELECTOR_SERVICE}.", flush=True)
            _STOP_REQUESTED = True
            return 0

        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        print(f"[blackout] Failed to start {BOOT_SELECTOR_SERVICE}: {stderr}", file=sys.stderr, flush=True)
        return result.returncode

    if not BOOT_SELECTOR_SCRIPT.exists():
        print(f"[blackout] Boot selector script not found: {BOOT_SELECTOR_SCRIPT}", file=sys.stderr, flush=True)
        return 1

    manual_env = os.environ.copy()
    manual_env.pop("INVOCATION_ID", None)
    subprocess.Popen(
        [sys.executable, "-u", str(BOOT_SELECTOR_SCRIPT)],
        cwd=str(BASE_DIR),
        env=manual_env,
        start_new_session=True,
    )
    print(f"[blackout] Long press detected; launched {BOOT_SELECTOR_SCRIPT} manually.", flush=True)
    _STOP_REQUESTED = True
    return 0


def load_icon(icon_path: Path, width: int, height: int) -> Image.Image:
    with Image.open(icon_path) as raw_icon:
        icon = raw_icon.convert("RGBA")

    if icon.width <= 0 or icon.height <= 0:
        raise ValueError("Icon has invalid dimensions")

    target = int(min(width, height) * ICON_SIZE_RATIO)
    target = max(ICON_MIN_SIZE, min(ICON_MAX_SIZE, target))
    resized = icon.copy()
    resized.thumbnail((target, target), RESAMPLING_LANCZOS)
    return resized


def load_time_font(width: int, height: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    target_height = max(28, int(height * 0.6))
    for candidate in FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(candidate, size=target_height)
            sample_bbox = font.getbbox("00:00")
            sample_width = sample_bbox[2] - sample_bbox[0]
            sample_height = sample_bbox[3] - sample_bbox[1]
            width_scale = width * 0.92
            height_scale = height * 0.72
            if sample_width <= 0 or sample_height <= 0:
                return font
            scale = min(width_scale / sample_width, height_scale / sample_height)
            fitted_size = max(28, int(target_height * scale))
            return ImageFont.truetype(candidate, size=fitted_size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_time_overlay(frame: Image.Image, width: int, height: int, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> None:
    draw = ImageDraw.Draw(frame)
    time_text = time.strftime("%H:%M")
    bbox = draw.textbbox((0, 0), time_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = (width - text_width) // 2 - bbox[0]
    text_y = (height - text_height) // 2 - bbox[1]
    draw.text((text_x, text_y), time_text, font=font, fill=TIME_TEXT_RGB)


def render_frame(
    width: int,
    height: int,
    icon: Image.Image,
    x: int,
    y: int,
    show_time: bool = False,
    time_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None,
) -> Image.Image:
    frame = Image.new("RGB", (width, height), (0, 0, 0))
    if show_time and time_font is not None:
        draw_time_overlay(frame, width, height, time_font)
    else:
        frame.paste(icon, (x, y), icon)
    return frame


def render_dirty_region(
    icon: Image.Image,
    previous_x: int,
    previous_y: int,
    x: int,
    y: int,
    icon_width: int,
    icon_height: int,
) -> tuple[Image.Image, int, int]:
    left = min(previous_x, x)
    top = min(previous_y, y)
    right = max(previous_x + icon_width, x + icon_width)
    bottom = max(previous_y + icon_height, y + icon_height)

    region = Image.new("RGB", (right - left, bottom - top), (0, 0, 0))
    region.paste(icon, (x - left, y - top), icon)
    return region, left, top


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
        icon = load_icon(icon_path, args.width, args.height)
    except Exception as exc:
        print(f"Unable to load icon {icon_path}: {exc}", file=sys.stderr)
        return 1

    icon_width, icon_height = icon.size
    x = 0
    y = 0
    vx = STEP_X
    vy = STEP_Y
    frame_interval = 1.0 / args.fps
    time_font = load_time_font(args.width, args.height)
    time_visible_until = 0.0
    previous_show_time = False
    touch_event_q: queue.Queue[str] = queue.Queue()
    touch_stop_evt = threading.Event()

    if not args.no_framebuffer:
        fb_path = Path(args.fbdev)
        if not fb_path.exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        threading.Thread(target=touch_worker, args=(touch_event_q, touch_stop_evt), daemon=True).start()

    preview_written = False

    try:
        if args.no_framebuffer:
            while not _STOP_REQUESTED:
                started = time.monotonic()
                show_time = time.monotonic() < time_visible_until
                frame = render_frame(args.width, args.height, icon, x, y, show_time=show_time, time_font=time_font)
                if args.output and not preview_written:
                    frame.save(args.output)
                    print(f"Saved preview image to {args.output}")
                    return 0

                x, y, vx, vy = advance_position(x, y, vx, vy, args.width, args.height, icon_width, icon_height)
                remaining = frame_interval - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)
            return 0

        with FramebufferWriter(args.fbdev, args.width, args.height) as framebuffer:
            framebuffer.clear()
            initial_frame = render_frame(args.width, args.height, icon, x, y)
            framebuffer.write_region(initial_frame, 0, 0)

            if args.output and not preview_written:
                initial_frame.save(args.output)
                print(f"Saved preview image to {args.output}")
                preview_written = True

            while not _STOP_REQUESTED:
                started = time.monotonic()
                while True:
                    try:
                        touch_event = touch_event_q.get_nowait()
                        if touch_event == "hold":
                            launch_status = activate_boot_selector()
                            if launch_status != 0:
                                return launch_status
                            return 0
                        time_visible_until = time.monotonic() + TIME_OVERLAY_SECS
                    except queue.Empty:
                        break

                show_time = time.monotonic() < time_visible_until
                previous_x = x
                previous_y = y
                x, y, vx, vy = advance_position(x, y, vx, vy, args.width, args.height, icon_width, icon_height)

                if show_time or previous_show_time:
                    frame = render_frame(args.width, args.height, icon, x, y, show_time=show_time, time_font=time_font)
                    framebuffer.write_region(frame, 0, 0)
                else:
                    dirty_frame, left, top = render_dirty_region(icon, previous_x, previous_y, x, y, icon_width, icon_height)
                    framebuffer.write_region(dirty_frame, left, top)

                previous_show_time = show_time
                remaining = frame_interval - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)
    except Exception as exc:
        print(f"Blackout animation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        touch_stop_evt.set()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

