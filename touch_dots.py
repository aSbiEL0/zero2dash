#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import mmap
import os
import re
import select
import struct
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
DOT_SIZE = 10
INPUT_EVENT_STRUCT = struct.Struct("llHHI")

EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03
ABS_X = 0x00
ABS_Y = 0x01
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39
BTN_TOUCH = 0x14A


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Draw black dots on a white framebuffer when the touchscreen is pressed.")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT)
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT)
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT)
    parser.add_argument("--touch-device", default=os.environ.get("TOUCH_DEVICE", ""))
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
    has_abs_y = bool(abs_mask & (1 << ABS_Y))
    has_abs_mt_x = bool(abs_mask & (1 << ABS_MT_POSITION_X))
    has_abs_mt_y = bool(abs_mask & (1 << ABS_MT_POSITION_Y))
    has_touch_abs = (has_abs_x and has_abs_y) or (has_abs_mt_x and has_abs_mt_y)
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


def select_touch_device(forced: str) -> str:
    if forced:
        if forced.startswith("event") and forced[5:].isdigit():
            forced = f"/dev/input/{forced}"
        if not Path(forced).exists():
            raise FileNotFoundError(f"Touch device not found: {forced}")
        print(f"[touch-dots] Using forced touch device {forced}", flush=True)
        return forced

    candidates = sorted(glob.glob("/dev/input/event*"))
    if not candidates:
        raise FileNotFoundError("No /dev/input/event* devices found")

    ranked: list[tuple[tuple[int, int, int, int], str, str]] = []
    for path in candidates:
        rank, reason = _touch_candidate_details(path)
        ranked.append((rank, path, reason))
    ranked.sort(reverse=True)

    best_rank, best_path, best_reason = ranked[0]
    if best_rank[0] <= 0:
        raise RuntimeError(f"No suitable touch device found. Best candidate: {best_path} ({best_reason})")

    print(f"[touch-dots] Using touch device {best_path} ({best_reason})", flush=True)
    return best_path


def _candidate_absinfo_paths(device: str) -> list[Path]:
    event_name = Path(device).name
    base = Path("/sys/class/input") / event_name / "device"
    candidates = [base / "absinfo"]
    for child in base.iterdir() if base.exists() else []:
        if child.name.startswith("input"):
            candidates.append(child / "absinfo")
    uniq: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            uniq.append(candidate)
    return uniq


def detect_abs_range(device: str, codes: tuple[int, ...]) -> tuple[int, int] | None:
    for absinfo_path in _candidate_absinfo_paths(device):
        try:
            with open(absinfo_path, encoding="utf-8") as absinfo:
                for line in absinfo:
                    code_str, _, payload = line.partition(":")
                    if not payload:
                        continue
                    try:
                        code = int(code_str.strip(), 16)
                    except ValueError:
                        try:
                            code = int(code_str.strip(), 0)
                        except ValueError:
                            continue
                    if code not in codes:
                        continue
                    parts = payload.strip().split()
                    if len(parts) < 3:
                        continue
                    min_val = int(parts[1])
                    max_val = int(parts[2])
                    if max_val > min_val:
                        return min_val, max_val
        except Exception:
            continue
    return None


def map_value(value: int, min_val: int, max_val: int, size: int) -> int:
    if max_val <= min_val:
        return max(0, min(size - 1, value))
    ratio = (value - min_val) / (max_val - min_val)
    pixel = int(round(ratio * (size - 1)))
    return max(0, min(size - 1, pixel))


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

    def __enter__(self) -> FramebufferWriter:
        self._handle = open(self.fbdev, "r+b", buffering=0)
        self._mapping = mmap.mmap(self._handle.fileno(), self.expected, mmap.MAP_SHARED, mmap.PROT_WRITE)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._mapping is not None:
            self._mapping.close()
        if self._handle is not None:
            self._handle.close()

    def write_frame(self, image: Image.Image) -> None:
        if self._mapping is None:
            raise RuntimeError("Framebuffer is not open")
        payload = rgb888_to_rgb565(image)
        self._mapping.seek(0)
        self._mapping.write(payload)

    def write_region(self, image: Image.Image, left: int, top: int) -> None:
        if self._mapping is None:
            raise RuntimeError("Framebuffer is not open")
        payload = rgb888_to_rgb565(image)
        row_bytes = image.width * 2
        for row in range(image.height):
            start = row * row_bytes
            end = start + row_bytes
            offset = (((top + row) * self.width) + left) * 2
            self._mapping.seek(offset)
            self._mapping.write(payload[start:end])


def make_dot_region(size: int) -> Image.Image:
    region = Image.new("RGB", (size, size), (255, 255, 255))
    draw = ImageDraw.Draw(region)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(0, 0, 0), outline=(0, 0, 0))
    return region


def main() -> int:
    args = parse_args()

    if args.width <= 0 or args.height <= 0:
        print("Width and height must be positive.", file=sys.stderr)
        return 1

    fb_path = Path(args.fbdev)
    if not fb_path.exists():
        print(f"Framebuffer not found: {args.fbdev}", file=sys.stderr)
        return 1

    try:
        touch_device = select_touch_device(args.touch_device)
    except Exception as exc:
        print(f"[touch-dots] {exc}", file=sys.stderr)
        return 1

    x_range = detect_abs_range(touch_device, (ABS_MT_POSITION_X, ABS_X)) or (0, args.width - 1)
    y_range = detect_abs_range(touch_device, (ABS_MT_POSITION_Y, ABS_Y)) or (0, args.height - 1)
    print(f"[touch-dots] X range {x_range[0]}..{x_range[1]}  Y range {y_range[0]}..{y_range[1]}", flush=True)
    print("[touch-dots] Press Ctrl+C to exit.", flush=True)

    frame = Image.new("RGB", (args.width, args.height), (255, 255, 255))
    dot_region = make_dot_region(DOT_SIZE)
    half = DOT_SIZE // 2

    last_x = 0
    last_y = 0
    touch_down = False

    with FramebufferWriter(args.fbdev, args.width, args.height) as framebuffer:
        framebuffer.write_frame(frame)

        with open(touch_device, "rb", buffering=0) as fd:
            try:
                while True:
                    readable, _, _ = select.select([fd], [], [], 0.2)
                    if not readable:
                        continue

                    raw = fd.read(INPUT_EVENT_STRUCT.size)
                    if len(raw) != INPUT_EVENT_STRUCT.size:
                        continue

                    _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)

                    if ev_type == EV_ABS:
                        if ev_code in (ABS_X, ABS_MT_POSITION_X):
                            last_x = map_value(ev_value, x_range[0], x_range[1], args.width)
                        elif ev_code in (ABS_Y, ABS_MT_POSITION_Y):
                            last_y = map_value(ev_value, y_range[0], y_range[1], args.height)
                        elif ev_code == ABS_MT_TRACKING_ID:
                            touch_down = ev_value >= 0
                    elif ev_type == EV_KEY and ev_code == BTN_TOUCH:
                        touch_down = ev_value == 1
                    elif ev_type == EV_SYN and touch_down:
                        left = max(0, min(args.width - DOT_SIZE, last_x - half))
                        top = max(0, min(args.height - DOT_SIZE, last_y - half))
                        frame.paste(dot_region, (left, top))
                        framebuffer.write_region(dot_region, left, top)
            except KeyboardInterrupt:
                print("\n[touch-dots] Exiting.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
