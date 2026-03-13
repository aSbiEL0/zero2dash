#!/usr/bin/env python3
"""Boot-time framebuffer selector with a 4-quadrant touch menu."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import fcntl
import glob
import mmap
import os
import re
import select
import shlex
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageSequence


FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
DEFAULT_GIF_PATH = os.environ.get("BOOT_SELECTOR_GIF_PATH", "boot/startup.gif")
DEFAULT_MAIN_MENU_IMAGE_PATH = os.environ.get("BOOT_SELECTOR_MAIN_MENU_IMAGE", "boot/mainmenu.png")
DEFAULT_SELECTOR_IMAGE_PATH = os.environ.get("BOOT_SELECTOR_DAY_NIGHT_IMAGE", os.environ.get("BOOT_SELECTOR_IMAGE_PATH", "boot/day-night.png"))
DEFAULT_SHUTDOWN_IMAGE_PATH = os.environ.get("BOOT_SELECTOR_SHUTDOWN_IMAGE", "boot/yes-no.png")
DEFAULT_KEYPAD_IMAGE_PATH = os.environ.get("BOOT_SELECTOR_KEYPAD_IMAGE", "boot/keypad.png")
DEFAULT_INFO_GIF_PATH = os.environ.get("BOOT_SELECTOR_INFO_GIF", "boot/credits.gif")
DEFAULT_GRANTED_GIF_PATH = os.environ.get("BOOT_SELECTOR_GRANTED_GIF", "boot/granted.gif")
DEFAULT_DENIED_GIF_PATH = os.environ.get("BOOT_SELECTOR_DENIED_GIF", "boot/denied.gif")
DEFAULT_SHUTDOWN_COMMAND = os.environ.get("BOOT_SELECTOR_SHUTDOWN_COMMAND", "systemctl poweroff")
DEFAULT_PLAYER_COMMAND = "/home/pihole/player.sh"
DEFAULT_PIN = os.environ.get("BOOT_SELECTOR_PIN", "")
DEFAULT_DAY_SERVICE = os.environ.get("BOOT_SELECTOR_DAY_SERVICE", "display.service")
DEFAULT_NIGHT_SERVICE = os.environ.get("BOOT_SELECTOR_NIGHT_SERVICE", "night.service")
DEFAULT_MAIN_MENU_REGIONS = os.environ.get("BOOT_SELECTOR_MAIN_MENU_REGIONS", "")
DEFAULT_DAY_NIGHT_REGIONS = os.environ.get("BOOT_SELECTOR_DAY_NIGHT_REGIONS", "")
DEFAULT_SHUTDOWN_REGIONS = os.environ.get("BOOT_SELECTOR_SHUTDOWN_REGIONS", "")
DEFAULT_KEYPAD_REGIONS = os.environ.get("BOOT_SELECTOR_KEYPAD_REGIONS", "")
DEFAULT_TOUCH_SETTLE_SECS = float(os.environ.get("BOOT_SELECTOR_TOUCH_SETTLE_SECS", "0.35"))
DEFAULT_TOUCH_DEBOUNCE_SECS = float(os.environ.get("BOOT_SELECTOR_TOUCH_DEBOUNCE_SECS", "0.35"))
DEFAULT_GIF_SPEED = float(os.environ.get("BOOT_SELECTOR_GIF_SPEED", "0.5"))
DEFAULT_TOUCH_INVERT_Y = os.environ.get("BOOT_SELECTOR_TOUCH_INVERT_Y", "0").strip().lower() not in {"0", "false", "no", "off"}
DEFAULT_SHOW_TOUCH_ZONES = os.environ.get("BOOT_SELECTOR_SHOW_TOUCH_ZONES", "0").strip().lower() not in {"0", "false", "no", "off"}
DEFAULT_GIF_FRAME_MS = 100
BACKGROUND_RGB = (0, 0, 0)
RESAMPLING_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
STOP_REQUESTED = False
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import touch_calibration

DIRECT_MODE_COMMANDS = {
    "display.service": [sys.executable, "-u", str(BASE_DIR / "display_rotator.py")],
    "night.service": [sys.executable, "-u", str(BASE_DIR / "modules" / "blackout" / "blackout.py")],
}
MAIN_MENU_HOME = "home"
MAIN_MENU_INFO = "info"
MAIN_MENU_PADLOCK = "padlock"
MAIN_MENU_SHUTDOWN = "shutdown"
DAY_NIGHT_DAY = "day"
DAY_NIGHT_NIGHT = "night"
SHUTDOWN_CONFIRM = "confirm"
SHUTDOWN_CANCEL = "cancel"
INFO_SKIP_ACTION = "menu"
KEYPAD_OK = "ok"
KEYPAD_NO = "no"
KEYPAD_DIGITS = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0"}
MAX_PIN_FAILURES = 3

EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03
ABS_X = 0x00
ABS_Y = 0x01
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39
BTN_TOUCH = 0x14A
INPUT_EVENT_STRUCT = struct.Struct("llHHI")
INPUT_ABSINFO_STRUCT = struct.Struct("iiiiii")

IOC_NRBITS = 8
IOC_TYPEBITS = 8
IOC_SIZEBITS = 14
IOC_DIRBITS = 2
IOC_NRSHIFT = 0
IOC_TYPESHIFT = IOC_NRSHIFT + IOC_NRBITS
IOC_SIZESHIFT = IOC_TYPESHIFT + IOC_TYPEBITS
IOC_DIRSHIFT = IOC_SIZESHIFT + IOC_SIZEBITS
IOC_READ = 2


@dataclass(frozen=True)
class TouchRegion:
    action: str
    left: int
    top: int
    right: int
    bottom: int

    def contains(self, screen_x: int, screen_y: int) -> bool:
        return self.left <= screen_x <= self.right and self.top <= screen_y <= self.bottom



def request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def _ioc(direction: int, ioc_type: int, number: int, size: int) -> int:
    return (direction << IOC_DIRSHIFT) | (ioc_type << IOC_TYPESHIFT) | (number << IOC_NRSHIFT) | (size << IOC_SIZESHIFT)


def eviocgabs(axis: int) -> int:
    return _ioc(IOC_READ, ord("E"), 0x40 + axis, INPUT_ABSINFO_STRUCT.size)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play a boot GIF once, then show a touch selector menu.")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
    parser.add_argument("--gif", default=DEFAULT_GIF_PATH, help=f"Startup GIF path (default: {DEFAULT_GIF_PATH})")
    parser.add_argument("--main-menu-image", default=DEFAULT_MAIN_MENU_IMAGE_PATH, help=f"Main menu image path (default: {DEFAULT_MAIN_MENU_IMAGE_PATH})")
    parser.add_argument("--selector-image", default=DEFAULT_SELECTOR_IMAGE_PATH, help=f"Day/night selector image path (default: {DEFAULT_SELECTOR_IMAGE_PATH})")
    parser.add_argument("--shutdown-image", default=DEFAULT_SHUTDOWN_IMAGE_PATH, help=f"Shutdown confirmation image path (default: {DEFAULT_SHUTDOWN_IMAGE_PATH})")
    parser.add_argument("--keypad-image", default=DEFAULT_KEYPAD_IMAGE_PATH, help=f"Keypad image path (default: {DEFAULT_KEYPAD_IMAGE_PATH})")
    parser.add_argument("--info-gif", default=DEFAULT_INFO_GIF_PATH, help=f"Info GIF path (default: {DEFAULT_INFO_GIF_PATH})")
    parser.add_argument("--granted-gif", default=DEFAULT_GRANTED_GIF_PATH, help=f"Granted GIF path (default: {DEFAULT_GRANTED_GIF_PATH})")
    parser.add_argument("--denied-gif", default=DEFAULT_DENIED_GIF_PATH, help=f"Denied GIF path (default: {DEFAULT_DENIED_GIF_PATH})")
    parser.add_argument("--gif-speed", type=float, default=DEFAULT_GIF_SPEED, help=f"GIF playback speed multiplier (default: {DEFAULT_GIF_SPEED})")
    parser.add_argument("--invert-y", action="store_true", default=DEFAULT_TOUCH_INVERT_Y, help="Invert the touch Y axis when deciding top/bottom selection.")
    parser.add_argument("--no-invert-y", action="store_false", dest="invert_y", help="Disable Y-axis inversion for top/bottom selection.")
    parser.add_argument("--output-selector", help="Optional output path for the rendered day/night selector screen.")
    parser.add_argument("--output-gif-first", help="Optional output path for the first rendered startup GIF frame.")
    parser.add_argument("--output-gif-last", help="Optional output path for the last rendered startup GIF frame.")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer writes for local verification.")
    parser.add_argument("--skip-gif", action="store_true", help="Skip startup GIF playback and show the menu immediately.")
    parser.add_argument("--probe-touch", action="store_true", help="Probe touch device selection and exit.")
    parser.add_argument("--touch-settle-secs", type=float, default=DEFAULT_TOUCH_SETTLE_SECS, help=f"Ignore touches briefly after each screen draw (default: {DEFAULT_TOUCH_SETTLE_SECS})")
    parser.add_argument("--touch-debounce-secs", type=float, default=DEFAULT_TOUCH_DEBOUNCE_SECS, help=f"Minimum interval between accepted taps (default: {DEFAULT_TOUCH_DEBOUNCE_SECS})")
    parser.add_argument("--day-service", default=DEFAULT_DAY_SERVICE, help=f"systemd unit to start for day mode (default: {DEFAULT_DAY_SERVICE})")
    parser.add_argument("--night-service", default=DEFAULT_NIGHT_SERVICE, help=f"systemd unit to start for night mode (default: {DEFAULT_NIGHT_SERVICE})")
    parser.add_argument("--shutdown-command", default=DEFAULT_SHUTDOWN_COMMAND, help=f"Command used for safe shutdown (default: {DEFAULT_SHUTDOWN_COMMAND})")
    parser.add_argument("--player-command", default=DEFAULT_PLAYER_COMMAND, help=f"Command used after entering the correct PIN (default: {DEFAULT_PLAYER_COMMAND}).")
    parser.add_argument("--pin", default=DEFAULT_PIN, help="PIN required by the padlock keypad.")
    parser.add_argument("--show-touch-zones", action="store_true", default=DEFAULT_SHOW_TOUCH_ZONES, help="Draw touch zone overlays on selector screens.")
    return parser.parse_args()


def shutdown_command_args(command_text: str) -> list[str]:
    return shlex.split(command_text)


def player_command_args(command_text: str) -> list[str]:
    return shlex.split(command_text)


def validate_args(args: argparse.Namespace) -> int | None:
    if args.width <= 0 or args.height <= 0:
        print("Width/height must be positive integers.", file=sys.stderr)
        return 1
    if args.touch_settle_secs < 0 or args.touch_debounce_secs < 0:
        print("Touch timing values cannot be negative.", file=sys.stderr)
        return 1
    if args.gif_speed <= 0:
        print("GIF speed must be greater than zero.", file=sys.stderr)
        return 1
    if not shutdown_command_args(args.shutdown_command):
        print("Shutdown command cannot be empty.", file=sys.stderr)
        return 1
    if not player_command_args(args.player_command):
        print("Player command cannot be empty.", file=sys.stderr)
        return 1
    return None


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
        self.expected = width * height * 2
        self._handle = None
        self._mapping = None

    def open(self) -> None:
        handle = open(self.fbdev, "r+b", buffering=0)
        mapping = mmap.mmap(handle.fileno(), self.expected, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self._handle = handle
        self._mapping = mapping

    def write_image(self, image: Image.Image) -> None:
        if self._mapping is None:
            raise RuntimeError("Framebuffer is not open")
        payload = rgb888_to_rgb565(image)
        if len(payload) != self.expected:
            raise RuntimeError(f"Framebuffer payload size mismatch: expected {self.expected} bytes, got {len(payload)} bytes")
        self._mapping.seek(0)
        self._mapping.write(payload)

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        if self._handle is not None:
            self._handle.close()
            self._handle = None


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
    name_bonus = 5 if "touchscreen" in name_lc else 3 if "touch" in name_lc else -3 if ("mouse" in name_lc or "keyboard" in name_lc) else 0
    score = (7 if has_touch_abs else -7) + (5 if has_btn_touch else -1) + name_bonus
    match = re.search(r"event(\d+)$", event_path)
    index = int(match.group(1)) if match else 999
    reason = f"score={score}; name='{name or 'unknown'}'; touch_abs={'yes' if has_touch_abs else 'no'}; BTN_TOUCH={'yes' if has_btn_touch else 'no'}"
    return (score, int(has_touch_abs), int(has_btn_touch), -index), reason


def _resolve_forced_touch_device() -> tuple[str | None, str | None]:
    forced = os.environ.get("TOUCH_DEVICE", "").strip() or os.environ.get("ROTATOR_TOUCH_DEVICE", "").strip()
    if not forced:
        return None, None
    resolved = f"/dev/input/{forced}" if forced.startswith("event") and forced[5:].isdigit() else forced
    if Path(resolved).exists():
        source = "TOUCH_DEVICE" if os.environ.get("TOUCH_DEVICE", "").strip() else "ROTATOR_TOUCH_DEVICE"
        return resolved, f"forced by {source}={forced}"
    return None, f"configured override '{forced}' was not found"


def touch_probe() -> tuple[str | None, str]:
    forced_path, forced_reason = _resolve_forced_touch_device()
    if forced_reason and forced_path is not None:
        return forced_path, forced_reason
    candidates = sorted(glob.glob("/dev/input/event*"))
    if not candidates:
        return None, "no /dev/input/event* devices found"
    ranked: list[tuple[tuple[int, int, int, int], str, str]] = []
    for path in candidates:
        rank, reason = _touch_candidate_details(path)
        ranked.append((rank, path, reason))
    ranked.sort(reverse=True)
    best_rank, best_path, best_reason = ranked[0]
    if best_rank[0] <= 0:
        details = "; ".join(f"{path}: {reason}" for _rank, path, reason in ranked)
        return None, f"no candidates scored above zero ({details})"
    return best_path, f"auto-selected highest rank ({best_reason})"


def select_touch_device() -> str | None:
    selected, reason = touch_probe()
    if selected:
        print(f"[boot-selector] Touch device selected: {selected} ({reason})", flush=True)
        return selected
    print(f"[boot-selector] Warning: no suitable touch input device found; touch controls disabled. Reason: {reason}.", flush=True)
    return None


def _candidate_absinfo_paths(device: str) -> list[Path]:
    event_name = Path(device).name
    base = Path("/sys/class/input") / event_name
    candidates = [base / "device" / "absinfo", base / "device" / "device" / "absinfo"]
    try:
        real = base.resolve()
        candidates.extend([real / "device" / "absinfo", real / "absinfo"])
    except Exception:
        pass
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique

def _query_absinfo(device: str, axis: int) -> tuple[int, int] | None:
    request = eviocgabs(axis)
    payload = bytearray(INPUT_ABSINFO_STRUCT.size)
    try:
        with open(device, "rb", buffering=0) as handle:
            fcntl.ioctl(handle.fileno(), request, payload, True)
    except Exception:
        return None
    _value, minimum, maximum, _fuzz, _flat, _resolution = INPUT_ABSINFO_STRUCT.unpack(bytes(payload))
    if maximum <= minimum:
        return None
    return minimum, maximum


def detect_touch_bounds(device: str, default_width: int, default_height: int) -> tuple[int, int, int, int]:
    x_bounds = _query_absinfo(device, ABS_X) or _query_absinfo(device, ABS_MT_POSITION_X)
    y_bounds = _query_absinfo(device, ABS_Y) or _query_absinfo(device, ABS_MT_POSITION_Y)
    if x_bounds is not None and y_bounds is not None:
        x_min, x_max = x_bounds
        y_min, y_max = y_bounds
        return (x_max - x_min + 1), x_min, (y_max - y_min + 1), y_min

    x_min = 0
    y_min = 0
    x_width = default_width
    y_height = default_height
    for absinfo_path in _candidate_absinfo_paths(device):
        try:
            with open(absinfo_path, encoding="utf-8") as absinfo:
                for line in absinfo:
                    code_str, _, payload = line.partition(":")
                    if not payload:
                        continue
                    try:
                        code = int(code_str.strip().lower(), 16)
                    except ValueError:
                        try:
                            code = int(code_str.strip(), 0)
                        except ValueError:
                            continue
                    parts = payload.strip().split()
                    if len(parts) < 3:
                        continue
                    min_val = int(parts[1])
                    max_val = int(parts[2])
                    if max_val <= min_val:
                        continue
                    size = max_val - min_val + 1
                    if code in (ABS_X, ABS_MT_POSITION_X):
                        x_min = min_val
                        x_width = max(100, size)
                    elif code in (ABS_Y, ABS_MT_POSITION_Y):
                        y_min = min_val
                        y_height = max(100, size)
        except Exception:
            continue
    return x_width, x_min, y_height, y_min


def _fit_frame(frame: Image.Image, width: int, height: int) -> Image.Image:
    converted = frame.convert("RGBA")
    source_width, source_height = converted.size
    scale = min(width / source_width, height / source_height)
    scaled_width = max(1, int(source_width * scale))
    scaled_height = max(1, int(source_height * scale))
    resized = converted.resize((scaled_width, scaled_height), RESAMPLING_LANCZOS)
    canvas = Image.new("RGBA", (width, height), BACKGROUND_RGB + (255,))
    canvas.alpha_composite(resized, ((width - scaled_width) // 2, (height - scaled_height) // 2))
    return canvas.convert("RGB")


def load_selector_image(image_path: Path, width: int, height: int) -> Image.Image:
    if image_path.exists():
        with Image.open(image_path) as selector_image:
            return _fit_frame(selector_image.copy(), width, height)
    print(f"[boot-selector] Selector image not found at {image_path}; using a blank screen.", flush=True)
    return Image.new("RGB", (width, height), BACKGROUND_RGB)


def load_gif_frames(gif_path: Path, width: int, height: int, speed: float) -> list[tuple[Image.Image, float]]:
    with Image.open(gif_path) as gif:
        frames: list[tuple[Image.Image, float]] = []
        for frame in ImageSequence.Iterator(gif):
            duration_ms = max(20, int(frame.info.get("duration", DEFAULT_GIF_FRAME_MS)))
            frames.append((_fit_frame(frame.copy(), width, height), (duration_ms / 1000.0) / speed))
        return frames


def save_preview(image: Image.Image, path_like: str | None) -> None:
    if not path_like:
        return
    output_path = Path(path_like)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    print(f"Saved preview image to {output_path}", flush=True)



def _make_region(action: str, left: int, top: int, right: int, bottom: int) -> TouchRegion:
    return TouchRegion(action=action, left=left, top=top, right=right, bottom=bottom)


def main_menu_regions(screen_width: int, screen_height: int) -> list[TouchRegion]:
    mid_x = screen_width // 2
    mid_y = screen_height // 2
    return [
        _make_region(MAIN_MENU_HOME, 0, 0, max(0, mid_x - 1), max(0, mid_y - 1)),
        _make_region(MAIN_MENU_INFO, mid_x, 0, max(0, screen_width - 1), max(0, mid_y - 1)),
        _make_region(MAIN_MENU_PADLOCK, 0, mid_y, max(0, mid_x - 1), max(0, screen_height - 1)),
        _make_region(MAIN_MENU_SHUTDOWN, mid_x, mid_y, max(0, screen_width - 1), max(0, screen_height - 1)),
    ]


def vertical_regions(screen_width: int, screen_height: int, invert_y: bool, top_action: str, bottom_action: str) -> list[TouchRegion]:
    mid_y = screen_height // 2
    top_region = _make_region(top_action, 0, 0, max(0, screen_width - 1), max(0, mid_y - 1))
    bottom_region = _make_region(bottom_action, 0, mid_y, max(0, screen_width - 1), max(0, screen_height - 1))
    return [bottom_region, top_region] if invert_y else [top_region, bottom_region]


def keypad_regions(screen_width: int, screen_height: int) -> list[TouchRegion]:
    keypad_rows = (
        ("1", "2", "3", KEYPAD_OK),
        ("4", "5", "6", "0"),
        ("7", "8", "9", KEYPAD_NO),
    )
    regions: list[TouchRegion] = []
    for row_index, row in enumerate(keypad_rows):
        top = row_index * screen_height // 3
        bottom = ((row_index + 1) * screen_height // 3) - 1 if row_index < 2 else max(0, screen_height - 1)
        for column_index, action in enumerate(row):
            left = column_index * screen_width // 4
            right = ((column_index + 1) * screen_width // 4) - 1 if column_index < 3 else max(0, screen_width - 1)
            regions.append(_make_region(action, left, top, right, bottom))
    return regions


def resolve_touch_region(screen_x: int, screen_y: int, regions: list[TouchRegion], label: str) -> str:
    for region in regions:
        if region.contains(screen_x, screen_y):
            return region.action
    raise RuntimeError(f"No {label} region matched screen_x={screen_x} screen_y={screen_y}")


def annotate_touch_regions(image: Image.Image, regions: list[TouchRegion], title: str) -> Image.Image:
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    colours = (
        (255, 80, 80),
        (80, 200, 255),
        (255, 210, 80),
        (120, 255, 120),
        (255, 120, 220),
        (255, 255, 255),
    )
    draw.text((4, 4), title, fill=(255, 255, 255))
    for index, region in enumerate(regions):
        colour = colours[index % len(colours)]
        draw.rectangle((region.left, region.top, region.right, region.bottom), outline=colour, width=2)
        label_x = min(max(0, region.left + 3), max(0, annotated.width - 48))
        label_y = min(max(12, region.top + 3), max(12, annotated.height - 12))
        draw.text((label_x, label_y), region.action, fill=colour)
    return annotated


def log_touch_regions(label: str, regions: list[TouchRegion]) -> None:
    for region in regions:
        print(
            f"[boot-selector] {label} zone {region.action}: left={region.left} top={region.top} right={region.right} bottom={region.bottom}",
            flush=True,
        )


def resolve_main_menu_action(screen_x: int, screen_y: int, screen_width: int, screen_height: int) -> str:
    return resolve_touch_region(screen_x, screen_y, main_menu_regions(screen_width, screen_height), "main menu")


def _resolve_vertical_zone(screen_y: int, screen_height: int, invert_y: bool, top_action: str, bottom_action: str) -> str:
    if invert_y:
        screen_y = (screen_height - 1) - screen_y
    return top_action if screen_y < (screen_height // 2) else bottom_action


def resolve_day_night_action(screen_y: int, screen_height: int, invert_y: bool) -> str:
    return resolve_touch_region(0, screen_y, vertical_regions(1, screen_height, invert_y, DAY_NIGHT_DAY, DAY_NIGHT_NIGHT), "day/night")


def resolve_shutdown_action(screen_y: int, screen_height: int, invert_y: bool) -> str:
    return resolve_touch_region(0, screen_y, vertical_regions(1, screen_height, invert_y, SHUTDOWN_CONFIRM, SHUTDOWN_CANCEL), "shutdown")


def resolve_keypad_action(screen_x: int, screen_y: int, screen_width: int, screen_height: int) -> str:
    return resolve_touch_region(screen_x, screen_y, keypad_regions(screen_width, screen_height), "keypad")

def evaluate_pin_entry(entered_pin: str, expected_pin: str, consecutive_failures: int, max_failures: int = MAX_PIN_FAILURES) -> tuple[str, int]:
    if entered_pin == expected_pin:
        return "success", 0
    updated_failures = consecutive_failures + 1
    if updated_failures >= max_failures:
        return "shutdown", updated_failures
    return "retry", updated_failures


def _normalise_axis(raw_value: int, source_size: int, source_min: int, target_size: int) -> int:
    relative = raw_value - source_min
    if relative < 0:
        relative = 0
    elif relative >= source_size:
        relative = source_size - 1
    if source_size <= 1:
        return 0
    return int(relative * (target_size - 1) / (source_size - 1))


def _map_touch_to_screen(device: str, raw_x: int, raw_y: int, screen_width: int, screen_height: int, touch_width: int, touch_min_x: int, touch_height: int, touch_min_y: int) -> tuple[int, int]:
    if touch_calibration.applies_to(device):
        return touch_calibration.map_to_screen(raw_x, raw_y, width=screen_width, height=screen_height)
    screen_x = _normalise_axis(raw_x, touch_width, touch_min_x, screen_width)
    screen_y = _normalise_axis(raw_y, touch_height, touch_min_y, screen_height)
    return screen_x, screen_y

class TouchReader:
    def __init__(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.device = select_touch_device()
        self.handle = None
        self.touch_width = screen_width
        self.touch_min_x = 0
        self.touch_height = screen_height
        self.touch_min_y = 0
        self.last_x = 0
        self.last_y = 0
        self.last_emit = 0.0
        self.touch_down = False
        if not self.device:
            return
        self.touch_width, self.touch_min_x, self.touch_height, self.touch_min_y = detect_touch_bounds(self.device, screen_width, screen_height)
        self.last_x = self.touch_min_x + (self.touch_width // 2)
        self.last_y = self.touch_min_y + (self.touch_height // 2)
        self.handle = open(self.device, "rb", buffering=0)

    def is_available(self) -> bool:
        return self.handle is not None and self.device is not None

    def describe(self) -> str:
        if not self.device:
            return "touch disabled"
        return f"{self.device} (width {self.touch_width}, height {self.touch_height})"

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def _commit_tap(self, now: float, ready_after: float, touch_debounce_secs: float, resolver) -> str | None:
        if self.device is None:
            return None
        if now < ready_after or (now - self.last_emit) < touch_debounce_secs:
            return None
        self.last_emit = now
        screen_x, screen_y = _map_touch_to_screen(
            self.device,
            self.last_x,
            self.last_y,
            self.screen_width,
            self.screen_height,
            self.touch_width,
            self.touch_min_x,
            self.touch_height,
            self.touch_min_y,
        )
        action = resolver(screen_x, screen_y)
        print(f"[boot-selector] Selected action: {action} (screen_x={screen_x}, screen_y={screen_y}, touch_x={self.last_x}, touch_y={self.last_y})", flush=True)
        return action

    def read_action(self, resolver, ready_after: float, touch_debounce_secs: float, timeout_secs: float | None = None) -> str | None:
        if self.handle is None:
            return None
        deadline = None if timeout_secs is None else time.monotonic() + timeout_secs
        while not STOP_REQUESTED:
            wait_timeout = 0.2
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                wait_timeout = min(wait_timeout, remaining)
            readable, _, _ = select.select([self.handle], [], [], wait_timeout)
            if not readable:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                continue
            raw = self.handle.read(INPUT_EVENT_STRUCT.size)
            if len(raw) != INPUT_EVENT_STRUCT.size:
                continue
            _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)
            if ev_type == EV_ABS and ev_code in (ABS_X, ABS_MT_POSITION_X):
                self.last_x = ev_value
            elif ev_type == EV_ABS and ev_code in (ABS_Y, ABS_MT_POSITION_Y):
                self.last_y = ev_value
            elif ev_type == EV_KEY and ev_code == BTN_TOUCH:
                if ev_value == 1:
                    self.touch_down = True
                elif ev_value == 0 and self.touch_down:
                    self.touch_down = False
                    action = self._commit_tap(time.monotonic(), ready_after, touch_debounce_secs, resolver)
                    if action is not None:
                        return action
            elif ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
                if ev_value == -1 and self.touch_down:
                    self.touch_down = False
                    action = self._commit_tap(time.monotonic(), ready_after, touch_debounce_secs, resolver)
                    if action is not None:
                        return action
                elif ev_value >= 0:
                    self.touch_down = True
        return None


def playback_gif(framebuffer: FramebufferWriter | None, gif_path: Path, width: int, height: int, speed: float, output_first: str | None, output_last: str | None, touch_reader: TouchReader | None = None, touch_settle_secs: float = 0.0, touch_debounce_secs: float = 0.0, skip_action: str | None = None) -> str | None:
    if not gif_path.exists():
        print(f"[boot-selector] GIF not found at {gif_path}; skipping animation.", flush=True)
        return None
    frames = load_gif_frames(gif_path, width, height, speed)
    if not frames:
        print(f"[boot-selector] GIF contains no frames: {gif_path}", flush=True)
        return None
    save_preview(frames[0][0], output_first)
    save_preview(frames[-1][0], output_last)
    if framebuffer is None:
        return None

    ready_after = time.monotonic() + max(0.0, touch_settle_secs)
    resolver = (lambda _screen_x, _screen_y: skip_action) if skip_action is not None else None
    for frame, duration in frames:
        if STOP_REQUESTED:
            return None
        framebuffer.write_image(frame)
        deadline = time.monotonic() + duration
        while not STOP_REQUESTED:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if touch_reader is None or resolver is None:
                time.sleep(remaining)
                break
            action = touch_reader.read_action(resolver, ready_after, touch_debounce_secs, timeout_secs=min(0.05, remaining))
            if action is not None:
                return action
    return None


def wait_for_action(touch_reader: TouchReader, label: str, resolver, touch_settle_secs: float, touch_debounce_secs: float) -> str | None:
    if not touch_reader.is_available():
        print("[boot-selector] No touch device found; touch controls disabled.", flush=True)
        return None
    print(f"[boot-selector] Waiting for {label} on {touch_reader.describe()}.", flush=True)
    ready_after = time.monotonic() + max(0.0, touch_settle_secs)
    return touch_reader.read_action(resolver, ready_after, touch_debounce_secs)


def run_touch_probe(width: int, height: int) -> int:
    device, reason = touch_probe()
    if not device:
        print("[boot-selector] Touch probe found no usable device.", flush=True)
        print(f"[boot-selector] Probe reason: {reason}", flush=True)
        return 1
    touch_width, touch_min_x, touch_height, touch_min_y = detect_touch_bounds(device, width, height)
    print(f"[boot-selector] Touch probe selected {device}", flush=True)
    print(f"[boot-selector] Probe reason: {reason}", flush=True)
    print(f"[boot-selector] Probe calibration: width={touch_width} min_x={touch_min_x} height={touch_height} min_y={touch_min_y}", flush=True)
    return 0


def _launch_direct_mode(service_name: str) -> int:
    command = DIRECT_MODE_COMMANDS.get(service_name)
    if not command:
        print(f"[boot-selector] No direct-launch fallback is defined for {service_name}.", file=sys.stderr, flush=True)
        return 1
    print(f"[boot-selector] Falling back to direct launch for {service_name}: {command}", flush=True)
    os.execv(command[0], command)
    return 1


def launch_service(service_name: str) -> int:
    running_under_systemd = bool(os.environ.get("INVOCATION_ID", "").strip())
    if not running_under_systemd:
        print(f"[boot-selector] Manual run detected; bypassing systemctl for {service_name}.", flush=True)
        return _launch_direct_mode(service_name)
    result = subprocess.run(["systemctl", "start", service_name], check=False, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[boot-selector] Started {service_name}", flush=True)
        return 0
    stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
    print(f"[boot-selector] Failed to start {service_name}: {stderr}", file=sys.stderr, flush=True)
    auth_markers = ("Authentication is required", "polkit", "Access denied", "Interactive authentication required")
    if any(marker.lower() in stderr.lower() for marker in auth_markers):
        return _launch_direct_mode(service_name)
    return result.returncode


def run_shutdown(command_text: str) -> int:
    command = shutdown_command_args(command_text)
    if not command:
        print("[boot-selector] Shutdown command is empty.", file=sys.stderr, flush=True)
        return 1
    print(f"[boot-selector] Running shutdown command: {command}", flush=True)
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode == 0:
        print("[boot-selector] Shutdown command accepted.", flush=True)
        return 0
    stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
    print(f"[boot-selector] Shutdown command failed: {stderr}", file=sys.stderr, flush=True)
    return result.returncode

def run_player(command_text: str) -> int:
    command = player_command_args(command_text)
    if not command:
        print("[boot-selector] Player command is empty.", file=sys.stderr, flush=True)
        return 1
    print(f"[boot-selector] Running player command: {command}", flush=True)
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode == 0:
        print("[boot-selector] Player command completed successfully.", flush=True)
        return 0
    stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
    print(f"[boot-selector] Player command failed: {stderr}", file=sys.stderr, flush=True)
    return result.returncode

def main() -> int:
    args = parse_args()
    validation_error = validate_args(args)
    if validation_error is not None:
        return validation_error

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    if args.probe_touch:
        return run_touch_probe(args.width, args.height)

    main_menu_image = load_selector_image(Path(args.main_menu_image), args.width, args.height)
    selector_image = load_selector_image(Path(args.selector_image), args.width, args.height)
    shutdown_image = load_selector_image(Path(args.shutdown_image), args.width, args.height)
    keypad_image = load_selector_image(Path(args.keypad_image), args.width, args.height)
    main_regions = main_menu_regions(args.width, args.height)
    day_night_regions_map = vertical_regions(args.width, args.height, args.invert_y, DAY_NIGHT_DAY, DAY_NIGHT_NIGHT)
    shutdown_regions_map = vertical_regions(args.width, args.height, args.invert_y, SHUTDOWN_CONFIRM, SHUTDOWN_CANCEL)
    keypad_regions_map = keypad_regions(args.width, args.height)
    if args.show_touch_zones:
        log_touch_regions("main menu", main_regions)
        log_touch_regions("day/night", day_night_regions_map)
        log_touch_regions("shutdown", shutdown_regions_map)
        log_touch_regions("keypad", keypad_regions_map)
        main_menu_image = annotate_touch_regions(main_menu_image, main_regions, "Main menu zones")
        selector_image = annotate_touch_regions(selector_image, day_night_regions_map, "Day/night zones")
        shutdown_image = annotate_touch_regions(shutdown_image, shutdown_regions_map, "Shutdown zones")
        keypad_image = annotate_touch_regions(keypad_image, keypad_regions_map, "Keypad zones")
    blank_image = Image.new("RGB", (args.width, args.height), BACKGROUND_RGB)
    save_preview(selector_image, args.output_selector)

    framebuffer = None
    if not args.no_framebuffer:
        if not Path(args.fbdev).exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        framebuffer = FramebufferWriter(args.fbdev, args.width, args.height)
        framebuffer.open()

    touch_reader = TouchReader(args.width, args.height)
    consecutive_pin_failures = 0
    try:
        if not args.skip_gif:
            playback_gif(framebuffer, Path(args.gif), args.width, args.height, args.gif_speed, args.output_gif_first, args.output_gif_last)

        if args.no_framebuffer:
            print("Skipping touch loop because --no-framebuffer was set.", flush=True)
            return 0

        while not STOP_REQUESTED:
            if framebuffer is not None:
                framebuffer.write_image(main_menu_image)

            main_action = wait_for_action(
                touch_reader,
                "main menu selection",
                lambda screen_x, screen_y: resolve_main_menu_action(screen_x, screen_y, args.width, args.height),
                args.touch_settle_secs,
                args.touch_debounce_secs,
            )
            if main_action == MAIN_MENU_HOME:
                if framebuffer is not None:
                    framebuffer.write_image(selector_image)
                day_night_action = wait_for_action(
                    touch_reader,
                    "day/night selection",
                    lambda _screen_x, screen_y: resolve_day_night_action(screen_y, args.height, args.invert_y),
                    args.touch_settle_secs,
                    args.touch_debounce_secs,
                )
                if day_night_action == DAY_NIGHT_DAY:
                    return launch_service(args.day_service)
                if day_night_action == DAY_NIGHT_NIGHT:
                    return launch_service(args.night_service)
                return 1 if STOP_REQUESTED else 0

            if main_action == MAIN_MENU_INFO:
                playback_gif(
                    framebuffer,
                    Path(args.info_gif),
                    args.width,
                    args.height,
                    args.gif_speed,
                    None,
                    None,
                    touch_reader=touch_reader,
                    touch_settle_secs=args.touch_settle_secs,
                    touch_debounce_secs=args.touch_debounce_secs,
                    skip_action=INFO_SKIP_ACTION,
                )
                continue

            if main_action == MAIN_MENU_PADLOCK:
                entered_pin = ""
                while not STOP_REQUESTED:
                    if framebuffer is not None:
                        framebuffer.write_image(keypad_image)
                    keypad_action = wait_for_action(
                        touch_reader,
                        "keypad selection",
                        lambda screen_x, screen_y: resolve_keypad_action(screen_x, screen_y, args.width, args.height),
                        args.touch_settle_secs,
                        args.touch_debounce_secs,
                    )
                    if keypad_action in KEYPAD_DIGITS:
                        entered_pin += keypad_action
                        continue
                    if keypad_action == KEYPAD_NO:
                        break
                    if keypad_action == KEYPAD_OK:
                        result, consecutive_pin_failures = evaluate_pin_entry(entered_pin, args.pin, consecutive_pin_failures)
                        entered_pin = ""
                        if result == "success":
                            playback_gif(
                                framebuffer,
                                Path(args.granted_gif),
                                args.width,
                                args.height,
                                args.gif_speed,
                                None,
                                None,
                            )
                            return run_player(args.player_command)
                        if result == "retry":
                            playback_gif(
                                framebuffer,
                                Path(args.denied_gif),
                                args.width,
                                args.height,
                                args.gif_speed,
                                None,
                                None,
                            )
                            break
                        if result == "shutdown":
                            playback_gif(
                                framebuffer,
                                Path(args.denied_gif),
                                args.width,
                                args.height,
                                args.gif_speed,
                                None,
                                None,
                            )
                            return run_shutdown(args.shutdown_command)
                    return 1 if STOP_REQUESTED else 0
                continue

            if main_action == MAIN_MENU_SHUTDOWN:
                if framebuffer is not None:
                    framebuffer.write_image(shutdown_image)
                shutdown_action = wait_for_action(
                    touch_reader,
                    "shutdown confirmation",
                    lambda _screen_x, screen_y: resolve_shutdown_action(screen_y, args.height, args.invert_y),
                    args.touch_settle_secs,
                    args.touch_debounce_secs,
                )
                if shutdown_action == SHUTDOWN_CONFIRM:
                    if framebuffer is not None:
                        framebuffer.write_image(blank_image)
                    return run_shutdown(args.shutdown_command)
                if shutdown_action == SHUTDOWN_CANCEL:
                    continue
                return 1 if STOP_REQUESTED else 0

            return 1 if STOP_REQUESTED else 0
        return 1 if STOP_REQUESTED else 0
    finally:
        touch_reader.close()
        if framebuffer is not None:
            framebuffer.close()


if __name__ == "__main__":
    raise SystemExit(main())

