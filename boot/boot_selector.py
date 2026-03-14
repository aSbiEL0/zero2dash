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
import tempfile
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
DEFAULT_PLAYER_COMMAND = "/home/pihole/zero2dash/player.sh"
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
DEFAULT_MODE_CONTROL_FILE = os.environ.get("BOOT_SELECTOR_MODE_CONTROL_FILE", str(Path(tempfile.gettempdir()) / "zero2dash-shell-mode"))
DEFAULT_HOME_HOLD_SECS = float(os.environ.get("BOOT_SELECTOR_HOME_HOLD_SECS", "1.5"))
DEFAULT_HOME_CORNER_SIZE = int(os.environ.get("BOOT_SELECTOR_HOME_CORNER_SIZE", "56"))
DEFAULT_APP_TERMINATE_GRACE_SECS = float(os.environ.get("BOOT_SELECTOR_APP_TERMINATE_GRACE_SECS", "5.0"))
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
DEFAULT_DASHBOARDS_COMMAND = os.environ.get("BOOT_SELECTOR_DASHBOARDS_COMMAND", shlex.join(DIRECT_MODE_COMMANDS[DEFAULT_DAY_SERVICE]))
DEFAULT_PHOTOS_COMMAND = os.environ.get(
    "BOOT_SELECTOR_PHOTOS_COMMAND",
    shlex.join([sys.executable, "-u", str(BASE_DIR / "modules" / "photos" / "display.py")]),
)
DEFAULT_NIGHT_COMMAND = os.environ.get("BOOT_SELECTOR_NIGHT_COMMAND", shlex.join(DIRECT_MODE_COMMANDS[DEFAULT_NIGHT_SERVICE]))

STATE_BOOT_GIF = "boot_gif"
STATE_MAIN_MENU = "main_menu"
STATE_DAY_NIGHT_MENU = "day_night_menu"
STATE_KEYPAD = "keypad"
STATE_SHUTDOWN_CONFIRM = "shutdown_confirm"
STATE_RUNNING_APP = "running_app"

MODE_MENU = "menu"
MODE_DASHBOARDS = "dashboards"
MODE_PHOTOS = "photos"
MODE_NIGHT = "night"
SUPPORTED_MODES = (MODE_MENU, MODE_DASHBOARDS, MODE_PHOTOS, MODE_NIGHT)

SHUTDOWN_CONFIRM = "confirm"
SHUTDOWN_CANCEL = "cancel"
INFO_SKIP_ACTION = "menu"
KEYPAD_OK = "ok"
KEYPAD_NO = "no"
KEYPAD_DIGITS = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0"}
MAX_PIN_FAILURES = 3
MENU_ACTION_NEXT = "__menu_next__"
MENU_ACTION_PREVIOUS = "__menu_previous__"
MENU_PAGE_STATES = (STATE_MAIN_MENU, STATE_DAY_NIGHT_MENU)

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


@dataclass(frozen=True)
class AppSpec:
    id: str
    label: str
    menu_page: int
    tile_index: int
    kind: str
    launch_command: list[str] | None
    preview_asset: str
    supports_home_gesture: bool
    mode: str


@dataclass(frozen=True)
class MenuTile:
    action: str
    label: str
    preview_asset: str
    kind: str



def request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def _ioc(direction: int, ioc_type: int, number: int, size: int) -> int:
    return (direction << IOC_DIRSHIFT) | (ioc_type << IOC_TYPESHIFT) | (number << IOC_NRSHIFT) | (size << IOC_SIZESHIFT)


def eviocgabs(axis: int) -> int:
    return _ioc(IOC_READ, ord("E"), 0x40 + axis, INPUT_ABSINFO_STRUCT.size)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the zero2dash shell runtime.")
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
    parser.add_argument("--day-service", default=DEFAULT_DAY_SERVICE, help=f"Legacy dashboards service name (default: {DEFAULT_DAY_SERVICE})")
    parser.add_argument("--night-service", default=DEFAULT_NIGHT_SERVICE, help=f"Legacy night service name (default: {DEFAULT_NIGHT_SERVICE})")
    parser.add_argument("--dashboards-command", default=DEFAULT_DASHBOARDS_COMMAND, help="Child command for the Dashboards app.")
    parser.add_argument("--photos-command", default=DEFAULT_PHOTOS_COMMAND, help="Child command for the Photos app.")
    parser.add_argument("--night-command", default=DEFAULT_NIGHT_COMMAND, help="Child command for the Night app.")
    parser.add_argument("--shutdown-command", default=DEFAULT_SHUTDOWN_COMMAND, help=f"Command used for safe shutdown (default: {DEFAULT_SHUTDOWN_COMMAND})")
    parser.add_argument("--player-command", default=DEFAULT_PLAYER_COMMAND, help=f"Command used after entering the correct PIN (default: {DEFAULT_PLAYER_COMMAND}).")
    parser.add_argument("--pin", default=DEFAULT_PIN, help="PIN required by the padlock keypad.")
    parser.add_argument("--show-touch-zones", action="store_true", default=DEFAULT_SHOW_TOUCH_ZONES, help="Draw touch zone overlays on selector screens.")
    parser.add_argument("--start-mode", choices=SUPPORTED_MODES, default=MODE_MENU, help="Mode to enter after startup.")
    parser.add_argument("--request-mode", choices=SUPPORTED_MODES, help="Write a mode-switch request for a running shell and exit.")
    parser.add_argument("--mode-control-file", default=DEFAULT_MODE_CONTROL_FILE, help=f"Control file used for mode requests (default: {DEFAULT_MODE_CONTROL_FILE})")
    parser.add_argument("--home-hold-secs", type=float, default=DEFAULT_HOME_HOLD_SECS, help=f"Hold duration for the global Home gesture while an app runs (default: {DEFAULT_HOME_HOLD_SECS})")
    parser.add_argument("--home-corner-size", type=int, default=DEFAULT_HOME_CORNER_SIZE, help=f"Reserved top-left Home gesture square in pixels (default: {DEFAULT_HOME_CORNER_SIZE})")
    parser.add_argument("--app-terminate-grace-secs", type=float, default=DEFAULT_APP_TERMINATE_GRACE_SECS, help=f"Grace period before force-killing child apps (default: {DEFAULT_APP_TERMINATE_GRACE_SECS})")
    return parser.parse_args()


def shell_command_args(command_text: str) -> list[str]:
    return shlex.split(command_text)


def shutdown_command_args(command_text: str) -> list[str]:
    return shell_command_args(command_text)


def player_command_args(command_text: str) -> list[str]:
    return shell_command_args(command_text)


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
    if args.home_hold_secs <= 0 or args.app_terminate_grace_secs < 0:
        print("Home-hold and app termination timings must be positive.", file=sys.stderr)
        return 1
    if args.home_corner_size <= 0:
        print("Home corner size must be positive.", file=sys.stderr)
        return 1
    if not shutdown_command_args(args.shutdown_command):
        print("Shutdown command cannot be empty.", file=sys.stderr)
        return 1
    if not player_command_args(args.player_command):
        print("Player command cannot be empty.", file=sys.stderr)
        return 1
    for label, command_text in (
        ("dashboards", args.dashboards_command),
        ("photos", args.photos_command),
        ("night", args.night_command),
    ):
        if not shell_command_args(command_text):
            print(f"{label.title()} command cannot be empty.", file=sys.stderr)
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


def load_preview_image(asset_path: Path, width: int, height: int) -> Image.Image | None:
    if not asset_path.exists():
        return None
    try:
        with Image.open(asset_path) as image:
            frame = next(ImageSequence.Iterator(image), image)
            return _fit_frame(frame.copy(), width, height)
    except Exception as exc:
        print(f"[boot-selector] Failed to load preview asset {asset_path}: {exc}", flush=True)
        return None


def save_preview(image: Image.Image, path_like: str | None) -> None:
    if not path_like:
        return
    output_path = Path(path_like)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    print(f"Saved preview image to {output_path}", flush=True)



def _make_region(action: str, left: int, top: int, right: int, bottom: int) -> TouchRegion:
    return TouchRegion(action=action, left=left, top=top, right=right, bottom=bottom)


def menu_tile_regions(screen_width: int, screen_height: int) -> list[TouchRegion]:
    mid_x = screen_width // 2
    mid_y = screen_height // 2
    return [
        _make_region("tile_0", 0, 0, max(0, mid_x - 1), max(0, mid_y - 1)),
        _make_region("tile_1", mid_x, 0, max(0, screen_width - 1), max(0, mid_y - 1)),
        _make_region("tile_2", 0, mid_y, max(0, mid_x - 1), max(0, screen_height - 1)),
        _make_region("tile_3", mid_x, mid_y, max(0, screen_width - 1), max(0, screen_height - 1)),
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


def _menu_state_for_page(page_index: int) -> str:
    return MENU_PAGE_STATES[max(0, min(page_index, len(MENU_PAGE_STATES) - 1))]


def _page_index_for_state(state: str) -> int:
    try:
        return MENU_PAGE_STATES.index(state)
    except ValueError:
        return 0


def resolve_launch_command(command_text: str, fallback_service: str | None = None) -> list[str]:
    command = shell_command_args(command_text)
    if command:
        return command
    if fallback_service and fallback_service in DIRECT_MODE_COMMANDS:
        return list(DIRECT_MODE_COMMANDS[fallback_service])
    return []


def build_app_registry(args: argparse.Namespace) -> dict[str, AppSpec]:
    return {
        MODE_DASHBOARDS: AppSpec(
            id=MODE_DASHBOARDS,
            label="Dashboards",
            menu_page=0,
            tile_index=0,
            kind="child_process",
            launch_command=resolve_launch_command(args.dashboards_command, args.day_service),
            preview_asset=args.main_menu_image,
            supports_home_gesture=True,
            mode=MODE_DASHBOARDS,
        ),
        "info": AppSpec(
            id="info",
            label="Info",
            menu_page=0,
            tile_index=1,
            kind="gif_screen",
            launch_command=None,
            preview_asset=args.info_gif,
            supports_home_gesture=False,
            mode=MODE_MENU,
        ),
        "keypad": AppSpec(
            id="keypad",
            label="Keypad",
            menu_page=0,
            tile_index=2,
            kind="shell_screen",
            launch_command=None,
            preview_asset=args.keypad_image,
            supports_home_gesture=False,
            mode=MODE_MENU,
        ),
        MODE_PHOTOS: AppSpec(
            id=MODE_PHOTOS,
            label="Photos",
            menu_page=1,
            tile_index=0,
            kind="child_process",
            launch_command=resolve_launch_command(args.photos_command),
            preview_asset=str(BASE_DIR / "modules" / "photos" / "photos-fallback.png"),
            supports_home_gesture=True,
            mode=MODE_PHOTOS,
        ),
        MODE_NIGHT: AppSpec(
            id=MODE_NIGHT,
            label="Night",
            menu_page=1,
            tile_index=1,
            kind="child_process",
            launch_command=resolve_launch_command(args.night_command, args.night_service),
            preview_asset=args.selector_image,
            supports_home_gesture=True,
            mode=MODE_NIGHT,
        ),
        "shutdown": AppSpec(
            id="shutdown",
            label="Shutdown",
            menu_page=1,
            tile_index=2,
            kind="shell_screen",
            launch_command=None,
            preview_asset=args.shutdown_image,
            supports_home_gesture=False,
            mode=MODE_MENU,
        ),
    }


def menu_tiles_for_page(page_index: int, registry: dict[str, AppSpec]) -> list[MenuTile]:
    tiles: list[MenuTile | None] = [None, None, None, None]
    for app in registry.values():
        if app.menu_page == page_index and 0 <= app.tile_index < 4:
            tiles[app.tile_index] = MenuTile(action=app.id, label=app.label, preview_asset=app.preview_asset, kind=app.kind)
    if page_index == 0:
        tiles[3] = MenuTile(action=MENU_ACTION_NEXT, label="More", preview_asset="", kind="navigation")
    else:
        tiles[3] = MenuTile(action=MENU_ACTION_PREVIOUS, label="Back", preview_asset="", kind="navigation")
    return [tile if tile is not None else MenuTile(action=MODE_MENU, label="", preview_asset="", kind="empty") for tile in tiles]


def render_menu_page(
    base_image: Image.Image,
    width: int,
    height: int,
    state: str,
    tiles: list[MenuTile],
    show_touch_zones: bool,
) -> Image.Image:
    canvas = base_image.convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, width - 1, 17), fill=(0, 0, 0, 180))
    draw.text((6, 4), f"Shell {_page_index_for_state(state) + 1}/{len(MENU_PAGE_STATES)}", fill=(255, 255, 255, 255))
    for index, region in enumerate(menu_tile_regions(width, height)):
        tile = tiles[index]
        fill = (0, 0, 0, 130) if tile.kind != "navigation" else (25, 25, 25, 150)
        outline = (255, 255, 255, 200)
        if tile.kind == "navigation":
            outline = (100, 180, 255, 220)
        elif tile.kind == "child_process":
            outline = (120, 255, 120, 220)
        elif tile.kind == "shell_screen":
            outline = (255, 210, 80, 220)
        elif tile.kind == "gif_screen":
            outline = (255, 120, 220, 220)
        draw.rectangle((region.left + 4, region.top + 4, region.right - 4, region.bottom - 4), fill=fill, outline=outline, width=2)
        if tile.preview_asset:
            preview = load_preview_image(Path(tile.preview_asset), max(1, region.right - region.left - 28), max(1, region.bottom - region.top - 46))
            if preview is not None:
                preview_width, preview_height = preview.size
                paste_x = region.left + ((region.right - region.left + 1) - preview_width) // 2
                paste_y = region.top + 16 + max(0, ((region.bottom - region.top - 28) - preview_height) // 2)
                canvas.alpha_composite(preview.convert("RGBA"), (paste_x, paste_y))
        label = tile.label or "Unavailable"
        draw.text((region.left + 10, max(region.top + 8, region.bottom - 18)), label, fill=(255, 255, 255, 255))
    rendered = canvas.convert("RGB")
    if show_touch_zones:
        rendered = annotate_touch_regions(rendered, menu_tile_regions(width, height), f"{state} zones")
    return rendered


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
        self.hold_started_at: float | None = None
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

    def _screen_position(self) -> tuple[int, int] | None:
        if self.device is None:
            return None
        return _map_touch_to_screen(
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

    def _reset_hold(self) -> None:
        self.hold_started_at = None

    def _check_hold(self, now: float, ready_after: float, region: TouchRegion, hold_secs: float) -> bool:
        if not self.touch_down or now < ready_after:
            self._reset_hold()
            return False
        screen_pos = self._screen_position()
        if screen_pos is None:
            self._reset_hold()
            return False
        screen_x, screen_y = screen_pos
        if not region.contains(screen_x, screen_y):
            self._reset_hold()
            return False
        if self.hold_started_at is None:
            self.hold_started_at = now
            return False
        if (now - self.hold_started_at) >= hold_secs:
            print(f"[boot-selector] Home gesture recognised at screen_x={screen_x}, screen_y={screen_y}.", flush=True)
            self._reset_hold()
            return True
        return False

    def _commit_tap(self, now: float, ready_after: float, touch_debounce_secs: float, resolver) -> str | None:
        if self.device is None:
            return None
        if now < ready_after or (now - self.last_emit) < touch_debounce_secs:
            return None
        self.last_emit = now
        screen_pos = self._screen_position()
        if screen_pos is None:
            return None
        screen_x, screen_y = screen_pos
        action = resolver(screen_x, screen_y)
        print(f"[boot-selector] Selected action: {action} (screen_x={screen_x}, screen_y={screen_y}, touch_x={self.last_x}, touch_y={self.last_y})", flush=True)
        return action

    def _process_input_event(self, raw: bytes) -> str:
        _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)
        if ev_type == EV_ABS and ev_code in (ABS_X, ABS_MT_POSITION_X):
            self.last_x = ev_value
            return "move"
        if ev_type == EV_ABS and ev_code in (ABS_Y, ABS_MT_POSITION_Y):
            self.last_y = ev_value
            return "move"
        if ev_type == EV_KEY and ev_code == BTN_TOUCH:
            if ev_value == 1:
                self.touch_down = True
                self._reset_hold()
                return "down"
            if ev_value == 0 and self.touch_down:
                self.touch_down = False
                self._reset_hold()
                return "up"
        if ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
            if ev_value == -1 and self.touch_down:
                self.touch_down = False
                self._reset_hold()
                return "up"
            if ev_value >= 0:
                self.touch_down = True
                self._reset_hold()
                return "down"
        return "other"

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
            event_kind = self._process_input_event(raw)
            if event_kind == "up":
                action = self._commit_tap(time.monotonic(), ready_after, touch_debounce_secs, resolver)
                if action is not None:
                    return action
        return None

    def wait_for_hold(self, region: TouchRegion, ready_after: float, hold_secs: float, timeout_secs: float) -> bool:
        if self.handle is None:
            time.sleep(timeout_secs)
            return False
        deadline = time.monotonic() + timeout_secs
        while not STOP_REQUESTED:
            now = time.monotonic()
            if self._check_hold(now, ready_after, region, hold_secs):
                return True
            remaining = deadline - now
            if remaining <= 0:
                return False
            readable, _, _ = select.select([self.handle], [], [], min(0.1, remaining))
            if not readable:
                continue
            raw = self.handle.read(INPUT_EVENT_STRUCT.size)
            if len(raw) != INPUT_EVENT_STRUCT.size:
                continue
            self._process_input_event(raw)
        return False


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


def write_mode_request(control_file: Path, mode: str) -> int:
    control_file.parent.mkdir(parents=True, exist_ok=True)
    temp_path = control_file.with_suffix(control_file.suffix + ".tmp")
    temp_path.write_text(f"{mode}\n", encoding="utf-8")
    temp_path.replace(control_file)
    print(f"[boot-selector] Requested shell mode '{mode}' via {control_file}.", flush=True)
    return 0


def consume_mode_request(control_file: Path) -> str | None:
    if not control_file.exists():
        return None
    try:
        mode = control_file.read_text(encoding="utf-8").strip()
    except Exception as exc:
        print(f"[boot-selector] Failed to read mode request {control_file}: {exc}", flush=True)
        return None
    try:
        control_file.unlink()
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"[boot-selector] Failed to clear mode request {control_file}: {exc}", flush=True)
    if mode not in SUPPORTED_MODES:
        print(f"[boot-selector] Ignoring unsupported mode request '{mode}'.", flush=True)
        return None
    print(f"[boot-selector] Consumed mode request '{mode}'.", flush=True)
    return mode


class AppRunner:
    def __init__(self, terminate_grace_secs: float) -> None:
        self.terminate_grace_secs = terminate_grace_secs
        self.process: subprocess.Popen | None = None
        self.spec: AppSpec | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, spec: AppSpec) -> None:
        if not spec.launch_command:
            raise RuntimeError(f"App {spec.id} has no launch command")
        self.stop(grace_override=0.0)
        env = os.environ.copy()
        env.setdefault("ZERO2DASH_ROOT", str(BASE_DIR))
        env.setdefault("PYTHONUNBUFFERED", "1")
        print(f"[boot-selector] Launching app {spec.id}: {spec.launch_command}", flush=True)
        self.process = subprocess.Popen(spec.launch_command, cwd=str(BASE_DIR), env=env)
        self.spec = spec

    def poll(self) -> int | None:
        if self.process is None:
            return None
        return self.process.poll()

    def stop(self, grace_override: float | None = None) -> None:
        if self.process is None:
            self.spec = None
            return
        grace_secs = self.terminate_grace_secs if grace_override is None else grace_override
        process = self.process
        spec = self.spec
        if process.poll() is None:
            print(f"[boot-selector] Stopping app {spec.id if spec else 'unknown'} gracefully.", flush=True)
            process.terminate()
            try:
                process.wait(timeout=max(0.1, grace_secs or 0.1))
            except subprocess.TimeoutExpired:
                print(f"[boot-selector] Force-killing app {spec.id if spec else 'unknown'} after timeout.", flush=True)
                process.kill()
                process.wait(timeout=5)
        else:
            process.wait(timeout=5)
        self.process = None
        self.spec = None


class ShellRuntime:
    def __init__(
        self,
        args: argparse.Namespace,
        framebuffer: FramebufferWriter | None,
        touch_reader: TouchReader,
        registry: dict[str, AppSpec],
        menu_images: dict[str, Image.Image],
        shutdown_image: Image.Image,
        keypad_image: Image.Image,
        blank_image: Image.Image,
    ) -> None:
        self.args = args
        self.framebuffer = framebuffer
        self.touch_reader = touch_reader
        self.registry = registry
        self.menu_images = menu_images
        self.shutdown_image = shutdown_image
        self.keypad_image = keypad_image
        self.blank_image = blank_image
        self.app_runner = AppRunner(args.app_terminate_grace_secs)
        self.state = STATE_BOOT_GIF
        self.last_menu_state = STATE_MAIN_MENU
        self.consecutive_pin_failures = 0
        corner = min(args.home_corner_size, args.width, args.height)
        self.home_region = _make_region(MODE_MENU, 0, 0, max(0, corner - 1), max(0, corner - 1))
        self.mode_control_file = Path(args.mode_control_file)

    def write_image(self, image: Image.Image) -> None:
        if self.framebuffer is not None:
            self.framebuffer.write_image(image)

    def apply_mode(self, mode: str, force: bool = False) -> int | None:
        if mode == MODE_MENU:
            if self.app_runner.is_running():
                self.app_runner.stop()
            self.state = self.last_menu_state if force else STATE_MAIN_MENU
            return None
        target = self.registry.get(mode)
        if target is None or target.kind != "child_process":
            print(f"[boot-selector] Mode {mode} is not bound to a child app.", flush=True)
            self.state = STATE_MAIN_MENU
            return None
        if self.app_runner.is_running() and self.app_runner.spec is not None and self.app_runner.spec.id == target.id and not force:
            return None
        if self.app_runner.is_running():
            self.app_runner.stop()
        self.last_menu_state = _menu_state_for_page(target.menu_page)
        self.app_runner.start(target)
        self.state = STATE_RUNNING_APP
        return None

    def run_menu_state(self) -> int | None:
        self.write_image(self.menu_images[self.state])
        if not self.touch_reader.is_available():
            time.sleep(0.2)
            return None
        tiles = menu_tiles_for_page(_page_index_for_state(self.state), self.registry)
        tile_regions = menu_tile_regions(self.args.width, self.args.height)
        action_map = {region.action: tiles[index].action for index, region in enumerate(tile_regions)}
        action = wait_for_action(
            self.touch_reader,
            f"{self.state} selection",
            lambda screen_x, screen_y: action_map[resolve_touch_region(screen_x, screen_y, tile_regions, self.state)],
            self.args.touch_settle_secs,
            self.args.touch_debounce_secs,
        )
        if action is None:
            return None
        if action == MENU_ACTION_NEXT:
            self.state = STATE_DAY_NIGHT_MENU
            self.last_menu_state = self.state
            return None
        if action == MENU_ACTION_PREVIOUS:
            self.state = STATE_MAIN_MENU
            self.last_menu_state = self.state
            return None
        return self.dispatch_action(action)

    def dispatch_action(self, action: str) -> int | None:
        spec = self.registry.get(action)
        if spec is None:
            print(f"[boot-selector] Ignoring unknown menu action '{action}'.", flush=True)
            return None
        self.last_menu_state = _menu_state_for_page(spec.menu_page)
        if spec.kind == "gif_screen":
            playback_gif(
                self.framebuffer,
                Path(self.args.info_gif),
                self.args.width,
                self.args.height,
                self.args.gif_speed,
                None,
                None,
                touch_reader=self.touch_reader,
                touch_settle_secs=self.args.touch_settle_secs,
                touch_debounce_secs=self.args.touch_debounce_secs,
                skip_action=INFO_SKIP_ACTION,
            )
            self.state = self.last_menu_state
            return None
        if spec.id == "keypad":
            self.state = STATE_KEYPAD
            return None
        if spec.id == "shutdown":
            self.state = STATE_SHUTDOWN_CONFIRM
            return None
        return self.apply_mode(spec.mode)

    def run_keypad_state(self) -> int | None:
        entered_pin = ""
        while not STOP_REQUESTED:
            self.write_image(self.keypad_image)
            keypad_action = wait_for_action(
                self.touch_reader,
                "keypad selection",
                lambda screen_x, screen_y: resolve_keypad_action(screen_x, screen_y, self.args.width, self.args.height),
                self.args.touch_settle_secs,
                self.args.touch_debounce_secs,
            )
            if keypad_action is None:
                return None
            if keypad_action in KEYPAD_DIGITS:
                entered_pin += keypad_action
                continue
            if keypad_action == KEYPAD_NO:
                self.state = self.last_menu_state
                return None
            if keypad_action == KEYPAD_OK:
                result, self.consecutive_pin_failures = evaluate_pin_entry(entered_pin, self.args.pin, self.consecutive_pin_failures)
                entered_pin = ""
                if result == "success":
                    playback_gif(self.framebuffer, Path(self.args.granted_gif), self.args.width, self.args.height, self.args.gif_speed, None, None)
                    unlocked_spec = AppSpec(
                        id="player",
                        label="Player",
                        menu_page=_page_index_for_state(self.last_menu_state),
                        tile_index=-1,
                        kind="child_process",
                        launch_command=player_command_args(self.args.player_command),
                        preview_asset="",
                        supports_home_gesture=True,
                        mode=MODE_MENU,
                    )
                    self.app_runner.start(unlocked_spec)
                    self.state = STATE_RUNNING_APP
                    return None
                if result == "retry":
                    playback_gif(self.framebuffer, Path(self.args.denied_gif), self.args.width, self.args.height, self.args.gif_speed, None, None)
                    self.state = self.last_menu_state
                    return None
                if result == "shutdown":
                    playback_gif(self.framebuffer, Path(self.args.denied_gif), self.args.width, self.args.height, self.args.gif_speed, None, None)
                    self.write_image(self.blank_image)
                    return run_shutdown(self.args.shutdown_command)
        return 1 if STOP_REQUESTED else 0

    def run_shutdown_state(self) -> int | None:
        self.write_image(self.shutdown_image)
        shutdown_regions = vertical_regions(1, self.args.height, self.args.invert_y, SHUTDOWN_CONFIRM, SHUTDOWN_CANCEL)
        shutdown_action = wait_for_action(
            self.touch_reader,
            "shutdown confirmation",
            lambda _screen_x, screen_y: resolve_touch_region(0, screen_y, shutdown_regions, "shutdown"),
            self.args.touch_settle_secs,
            self.args.touch_debounce_secs,
        )
        if shutdown_action == SHUTDOWN_CONFIRM:
            self.write_image(self.blank_image)
            return run_shutdown(self.args.shutdown_command)
        self.state = self.last_menu_state
        return None

    def run_child_app_state(self) -> int | None:
        ready_after = time.monotonic() + max(0.0, self.args.touch_settle_secs)
        while not STOP_REQUESTED and self.app_runner.spec is not None:
            requested_mode = consume_mode_request(self.mode_control_file)
            if requested_mode is not None:
                return self.apply_mode(requested_mode)
            exit_code = self.app_runner.poll()
            if exit_code is not None:
                print(f"[boot-selector] App {self.app_runner.spec.id} exited with code {exit_code}.", flush=True)
                self.app_runner.stop(grace_override=0.0)
                self.state = self.last_menu_state
                return None
            current_spec = self.app_runner.spec
            if current_spec.supports_home_gesture and self.touch_reader.wait_for_hold(
                self.home_region,
                ready_after,
                self.args.home_hold_secs,
                timeout_secs=0.2,
            ):
                self.app_runner.stop()
                self.state = self.last_menu_state
                return None
            if not current_spec.supports_home_gesture:
                time.sleep(0.2)
        self.state = self.last_menu_state
        return None

    def run(self, start_mode: str) -> int:
        self.apply_mode(start_mode, force=True)
        while not STOP_REQUESTED:
            requested_mode = consume_mode_request(self.mode_control_file)
            if requested_mode is not None:
                result = self.apply_mode(requested_mode)
                if result is not None:
                    return result
                continue
            if self.state in MENU_PAGE_STATES:
                result = self.run_menu_state()
            elif self.state == STATE_KEYPAD:
                result = self.run_keypad_state()
            elif self.state == STATE_SHUTDOWN_CONFIRM:
                result = self.run_shutdown_state()
            elif self.state == STATE_RUNNING_APP:
                result = self.run_child_app_state()
            else:
                self.state = STATE_MAIN_MENU
                result = None
            if result is not None:
                return result
        return 1 if STOP_REQUESTED else 0

    def close(self) -> None:
        self.app_runner.stop(grace_override=0.0)


def main() -> int:
    args = parse_args()
    validation_error = validate_args(args)
    if validation_error is not None:
        return validation_error

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    if args.request_mode:
        return write_mode_request(Path(args.mode_control_file), args.request_mode)

    if args.probe_touch:
        return run_touch_probe(args.width, args.height)

    main_menu_background = load_selector_image(Path(args.main_menu_image), args.width, args.height)
    selector_background = load_selector_image(Path(args.selector_image), args.width, args.height)
    shutdown_image = load_selector_image(Path(args.shutdown_image), args.width, args.height)
    keypad_image = load_selector_image(Path(args.keypad_image), args.width, args.height)

    registry = build_app_registry(args)
    menu_images = {
        STATE_MAIN_MENU: render_menu_page(main_menu_background, args.width, args.height, STATE_MAIN_MENU, menu_tiles_for_page(0, registry), args.show_touch_zones),
        STATE_DAY_NIGHT_MENU: render_menu_page(selector_background, args.width, args.height, STATE_DAY_NIGHT_MENU, menu_tiles_for_page(1, registry), args.show_touch_zones),
    }
    shutdown_regions_map = vertical_regions(args.width, args.height, args.invert_y, SHUTDOWN_CONFIRM, SHUTDOWN_CANCEL)
    keypad_regions_map = keypad_regions(args.width, args.height)
    home_size = min(args.home_corner_size, args.width, args.height)
    home_region = _make_region(MODE_MENU, 0, 0, max(0, home_size - 1), max(0, home_size - 1))
    if args.show_touch_zones:
        log_touch_regions("menu page 1", menu_tile_regions(args.width, args.height))
        log_touch_regions("menu page 2", menu_tile_regions(args.width, args.height))
        log_touch_regions("shutdown", shutdown_regions_map)
        log_touch_regions("keypad", keypad_regions_map)
        log_touch_regions("home hold", [home_region])
        shutdown_image = annotate_touch_regions(shutdown_image, shutdown_regions_map, "Shutdown zones")
        keypad_image = annotate_touch_regions(keypad_image, keypad_regions_map, "Keypad zones")
    blank_image = Image.new("RGB", (args.width, args.height), BACKGROUND_RGB)
    save_preview(menu_images[STATE_DAY_NIGHT_MENU], args.output_selector)

    framebuffer = None
    if not args.no_framebuffer:
        if not Path(args.fbdev).exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        framebuffer = FramebufferWriter(args.fbdev, args.width, args.height)
        framebuffer.open()

    touch_reader = TouchReader(args.width, args.height)
    runtime = ShellRuntime(args, framebuffer, touch_reader, registry, menu_images, shutdown_image, keypad_image, blank_image)
    try:
        if not args.skip_gif:
            playback_gif(framebuffer, Path(args.gif), args.width, args.height, args.gif_speed, args.output_gif_first, args.output_gif_last)

        if args.no_framebuffer:
            print("[boot-selector] Shell registry:", flush=True)
            for app in registry.values():
                print(
                    f"[boot-selector] app id={app.id} label={app.label} page={app.menu_page} tile={app.tile_index} kind={app.kind} command={app.launch_command}",
                    flush=True,
                )
            print("[boot-selector] Skipping shell loop because --no-framebuffer was set.", flush=True)
            return 0

        return runtime.run(args.start_mode)
    finally:
        runtime.close()
        touch_reader.close()
        if framebuffer is not None:
            framebuffer.close()


if __name__ == "__main__":
    raise SystemExit(main())
