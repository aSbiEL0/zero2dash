#!/usr/bin/env python3
"""Boot-time framebuffer shell with a paged 4-tile touch menu."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import fcntl
import glob
import json
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
DEFAULT_CHILD_STOP_GRACE_SECS = float(os.environ.get("BOOT_SELECTOR_CHILD_STOP_GRACE_SECS", "3.0"))
DEFAULT_HOME_GESTURE_HOLD_SECS = float(os.environ.get("BOOT_SELECTOR_HOME_GESTURE_HOLD_SECS", "1.5"))
DEFAULT_HOME_GESTURE_CORNER_WIDTH = int(os.environ.get("BOOT_SELECTOR_HOME_GESTURE_CORNER_WIDTH", "64"))
DEFAULT_HOME_GESTURE_CORNER_HEIGHT = int(os.environ.get("BOOT_SELECTOR_HOME_GESTURE_CORNER_HEIGHT", "48"))
DEFAULT_MODE_REQUEST_PATH = os.environ.get(
    "BOOT_SELECTOR_MODE_REQUEST_PATH",
    str(Path(tempfile.gettempdir()) / "zero2dash-shell-mode-request"),
)
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
SHELL_MODE_MENU = "menu"
SHELL_MODE_DASHBOARDS = "dashboards"
SHELL_MODE_PHOTOS = "photos"
SHELL_MODE_NIGHT = "night"
SHELL_MODES = (
    SHELL_MODE_MENU,
    SHELL_MODE_DASHBOARDS,
    SHELL_MODE_PHOTOS,
    SHELL_MODE_NIGHT,
)
SHELL_STATE_BOOT_GIF = "boot_gif"
SHELL_STATE_MAIN_MENU = "main_menu"
SHELL_STATE_DAY_NIGHT_MENU = "day_night_menu"
SHELL_STATE_KEYPAD = "keypad"
SHELL_STATE_SHUTDOWN_CONFIRM = "shutdown_confirm"
SHELL_STATE_RUNNING_APP = "running_app"
SHUTDOWN_CONFIRM = "confirm"
SHUTDOWN_CANCEL = "cancel"
INFO_SKIP_ACTION = "menu"
KEYPAD_OK = "ok"
KEYPAD_NO = "no"
KEYPAD_DIGITS = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0"}
MAX_PIN_FAILURES = 3
APP_KIND_CHILD_PROCESS = "child_process"
APP_KIND_SHELL_SCREEN = "shell_screen"
APP_ID_DASHBOARDS = "dashboards"
APP_ID_PHOTOS = "photos"
APP_ID_INFO = "info"
APP_ID_KEYPAD = "keypad"
APP_ID_SHUTDOWN = "shutdown"
INTERNAL_APP_ID_NIGHT = "night"
POLL_TIMEOUT_SECS = 0.2
MENU_TILES_PER_PAGE = 4
MENU_ACTION_NOOP = "menu_noop"
MENU_ACTION_PREV_PAGE = "menu_prev_page"
MENU_ACTION_NEXT_PAGE = "menu_next_page"
MENU_HEADER_HEIGHT = 20
MENU_FOOTER_HEIGHT = 28
MENU_MARGIN = 8
MENU_GAP = 8
MENU_ACCENT_RGB = (90, 180, 255)
MENU_BACKGROUND_TOP_RGB = (11, 18, 28)
MENU_BACKGROUND_BOTTOM_RGB = (24, 34, 48)
MENU_TILE_FILL_RGB = (26, 35, 48)
MENU_TILE_OUTLINE_RGB = (74, 110, 150)
MENU_TEXT_RGB = (244, 247, 250)
MENU_SUBTLE_TEXT_RGB = (180, 192, 206)

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
    launch_command: tuple[str, ...]
    preview_asset: str
    supports_home_gesture: bool

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "menu_page": self.menu_page,
            "tile_index": self.tile_index,
            "kind": self.kind,
            "launch_command": list(self.launch_command),
            "preview_asset": self.preview_asset,
            "supports_home_gesture": self.supports_home_gesture,
        }


@dataclass
class RunningChildApp:
    app: AppSpec
    process: subprocess.Popen[bytes] | subprocess.Popen[str]
    started_at: float


@dataclass(frozen=True)
class ShellImages:
    menu_pages: tuple[Image.Image, ...]
    shutdown: Image.Image
    keypad: Image.Image
    blank: Image.Image


@dataclass(frozen=True)
class MenuPage:
    page_index: int
    page_count: int
    tile_app_ids: tuple[str | None, ...]
    image: Image.Image


class ModeSwitchRequestStore:
    def __init__(self, path_like: str | Path) -> None:
        self.path = Path(path_like)

    def write_request(self, mode: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(f"{mode}\n", encoding="utf-8")
        os.replace(tmp_path, self.path)

    def consume_request(self) -> str | None:
        try:
            payload = self.path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        except OSError as exc:
            print(f"[boot-selector] Failed to read mode request {self.path}: {exc}", file=sys.stderr, flush=True)
            return None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"[boot-selector] Failed to clear mode request {self.path}: {exc}", file=sys.stderr, flush=True)
        if payload not in SHELL_MODES:
            print(f"[boot-selector] Ignoring invalid shell mode request: {payload!r}", file=sys.stderr, flush=True)
            return None
        print(f"[boot-selector] Consumed shell mode request: {payload}", flush=True)
        return payload


class ChildAppManager:
    def __init__(self, stop_grace_secs: float) -> None:
        self.stop_grace_secs = stop_grace_secs
        self._running: RunningChildApp | None = None

    def running_app(self) -> RunningChildApp | None:
        if self._running is None:
            return None
        return_code = self._running.process.poll()
        if return_code is None:
            return self._running
        print(
            f"[boot-selector] Child app {self._running.app.id} exited with code {return_code}. Returning control to shell.",
            flush=True,
        )
        self._running = None
        return None

    def is_running(self) -> bool:
        return self.running_app() is not None

    def start_app(self, app: AppSpec) -> bool:
        if app.kind != APP_KIND_CHILD_PROCESS:
            print(f"[boot-selector] App {app.id} is shell-owned and cannot be launched as a child process.", file=sys.stderr, flush=True)
            return False
        if not app.launch_command:
            print(f"[boot-selector] App {app.id} does not define a launch command.", file=sys.stderr, flush=True)
            return False
        current = self.running_app()
        if current is not None and current.app.id == app.id:
            print(f"[boot-selector] Child app {app.id} is already running.", flush=True)
            return True
        if current is not None:
            self.stop_current(reason=f"switching from {current.app.id} to {app.id}")
        print(f"[boot-selector] Starting child app {app.id}: {list(app.launch_command)}", flush=True)
        try:
            process = subprocess.Popen(list(app.launch_command))
        except OSError as exc:
            print(f"[boot-selector] Failed to start child app {app.id}: {exc}", file=sys.stderr, flush=True)
            return False
        self._running = RunningChildApp(app=app, process=process, started_at=time.monotonic())
        return True

    def stop_current(self, reason: str) -> bool:
        running = self.running_app()
        if running is None:
            return False
        process = running.process
        print(f"[boot-selector] Stopping child app {running.app.id}: {reason}", flush=True)
        try:
            process.terminate()
        except ProcessLookupError:
            self._running = None
            return True
        try:
            process.wait(timeout=self.stop_grace_secs)
        except subprocess.TimeoutExpired:
            print(f"[boot-selector] Child app {running.app.id} did not exit after SIGTERM; forcing termination.", flush=True)
            process.kill()
            process.wait(timeout=2.0)
        self._running = None
        return True

    def shutdown(self) -> None:
        self.stop_current(reason="shell shutdown")


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
    parser.add_argument("--dump-contracts", action="store_true", help="Print the Stream A shell contracts as JSON and exit.")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer writes for local verification.")
    parser.add_argument("--skip-gif", action="store_true", help="Skip startup GIF playback and show the menu immediately.")
    parser.add_argument("--probe-touch", action="store_true", help="Probe touch device selection and exit.")
    parser.add_argument("--request-mode", choices=SHELL_MODES, help="Write a shell mode-switch request for a running shell and exit.")
    parser.add_argument("--mode-request-path", default=DEFAULT_MODE_REQUEST_PATH, help=f"Path used for shell mode-switch requests (default: {DEFAULT_MODE_REQUEST_PATH})")
    parser.add_argument("--touch-settle-secs", type=float, default=DEFAULT_TOUCH_SETTLE_SECS, help=f"Ignore touches briefly after each screen draw (default: {DEFAULT_TOUCH_SETTLE_SECS})")
    parser.add_argument("--touch-debounce-secs", type=float, default=DEFAULT_TOUCH_DEBOUNCE_SECS, help=f"Minimum interval between accepted taps (default: {DEFAULT_TOUCH_DEBOUNCE_SECS})")
    parser.add_argument("--child-stop-grace-secs", type=float, default=DEFAULT_CHILD_STOP_GRACE_SECS, help=f"Seconds to wait for child apps to stop before force-killing them (default: {DEFAULT_CHILD_STOP_GRACE_SECS})")
    parser.add_argument("--home-gesture-hold-secs", type=float, default=DEFAULT_HOME_GESTURE_HOLD_SECS, help=f"Reserved-corner hold duration used to reclaim child apps (default: {DEFAULT_HOME_GESTURE_HOLD_SECS})")
    parser.add_argument("--home-gesture-corner-width", type=int, default=DEFAULT_HOME_GESTURE_CORNER_WIDTH, help=f"Width of the reserved home-gesture corner in pixels (default: {DEFAULT_HOME_GESTURE_CORNER_WIDTH})")
    parser.add_argument("--home-gesture-corner-height", type=int, default=DEFAULT_HOME_GESTURE_CORNER_HEIGHT, help=f"Height of the reserved home-gesture corner in pixels (default: {DEFAULT_HOME_GESTURE_CORNER_HEIGHT})")
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
    if args.child_stop_grace_secs < 0 or args.home_gesture_hold_secs < 0:
        print("Child-stop and home-gesture timing values cannot be negative.", file=sys.stderr)
        return 1
    if args.home_gesture_corner_width <= 0 or args.home_gesture_corner_height <= 0:
        print("Home-gesture corner dimensions must be positive integers.", file=sys.stderr)
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


def _command_for_service(service_name: str, fallback_command: list[str]) -> tuple[str, ...]:
    command = DIRECT_MODE_COMMANDS.get(service_name)
    if command is None:
        print(
            f"[boot-selector] No direct mapping is defined for {service_name}; using shell-owned fallback command {fallback_command}.",
            file=sys.stderr,
            flush=True,
        )
        command = fallback_command
    return tuple(command)


def build_app_registry(args: argparse.Namespace) -> dict[str, AppSpec]:
    return {
        APP_ID_DASHBOARDS: AppSpec(
            id=APP_ID_DASHBOARDS,
            label="Dashboards",
            menu_page=0,
            tile_index=0,
            kind=APP_KIND_CHILD_PROCESS,
            launch_command=_command_for_service(
                args.day_service,
                [sys.executable, "-u", str(BASE_DIR / "display_rotator.py")],
            ),
            preview_asset=args.selector_image,
            supports_home_gesture=True,
        ),
        APP_ID_INFO: AppSpec(
            id=APP_ID_INFO,
            label="Info GIF",
            menu_page=0,
            tile_index=1,
            kind=APP_KIND_SHELL_SCREEN,
            launch_command=(),
            preview_asset=args.info_gif,
            supports_home_gesture=False,
        ),
        APP_ID_KEYPAD: AppSpec(
            id=APP_ID_KEYPAD,
            label="Keypad",
            menu_page=0,
            tile_index=2,
            kind=APP_KIND_SHELL_SCREEN,
            launch_command=(),
            preview_asset=args.keypad_image,
            supports_home_gesture=False,
        ),
        APP_ID_SHUTDOWN: AppSpec(
            id=APP_ID_SHUTDOWN,
            label="Shutdown",
            menu_page=0,
            tile_index=3,
            kind=APP_KIND_SHELL_SCREEN,
            launch_command=(),
            preview_asset=args.shutdown_image,
            supports_home_gesture=False,
        ),
        APP_ID_PHOTOS: AppSpec(
            id=APP_ID_PHOTOS,
            label="Photos",
            menu_page=1,
            tile_index=0,
            kind=APP_KIND_CHILD_PROCESS,
            launch_command=(
                sys.executable,
                "-u",
                str(BASE_DIR / "modules" / "photos" / "slideshow.py"),
            ),
            preview_asset=str(BASE_DIR / "modules" / "photos" / "photos-fallback.png"),
            supports_home_gesture=True,
        ),
    }


def build_night_mode_app(args: argparse.Namespace) -> AppSpec:
    return AppSpec(
        id=INTERNAL_APP_ID_NIGHT,
        label="Night",
        menu_page=-1,
        tile_index=-1,
        kind=APP_KIND_CHILD_PROCESS,
        launch_command=_command_for_service(
            args.night_service,
            [sys.executable, "-u", str(BASE_DIR / "modules" / "blackout" / "blackout.py")],
        ),
        preview_asset=args.selector_image,
        supports_home_gesture=True,
    )


def build_contract_snapshot(
    app_registry: dict[str, AppSpec],
    night_app: AppSpec,
    mode_request_path: str,
    args: argparse.Namespace,
) -> dict[str, object]:
    ordered_registry = sorted(
        (app.to_contract_dict() for app in app_registry.values()),
        key=lambda item: (int(item["menu_page"]), int(item["tile_index"]), str(item["id"])),
    )
    return {
        "app_registry": ordered_registry,
        "menu": {
            "model": "paged_4_tile_shell_menu",
            "tiles_per_page": MENU_TILES_PER_PAGE,
            "page_count": max((app.menu_page for app in app_registry.values()), default=0) + 1,
        },
        "child_lifecycle": {
            "start": "ChildAppManager.start_app(app_spec)",
            "detect_running": "ChildAppManager.running_app() / is_running()",
            "graceful_stop": f"SIGTERM with {args.child_stop_grace_secs:.2f}s grace period",
            "forced_termination_fallback": "SIGKILL after the grace period if the child is still running",
            "clean_return_to_shell": "Shell returns to main_menu after child exit, Home hold, or menu mode request",
            "home_gesture": {
                "enabled_for_child_apps": True,
                "corner": {
                    "left": 0,
                    "top": 0,
                    "right": max(0, args.home_gesture_corner_width - 1),
                    "bottom": max(0, args.home_gesture_corner_height - 1),
                },
                "hold_secs": args.home_gesture_hold_secs,
            },
        },
        "mode_switch": {
            "modes": list(SHELL_MODES),
            "request_path": mode_request_path,
            "trigger_cli": "boot/boot_selector.py --request-mode <menu|dashboards|photos|night>",
            "mode_targets": {
                SHELL_MODE_MENU: {"shell_state": SHELL_STATE_MAIN_MENU},
                SHELL_MODE_DASHBOARDS: {"app_id": app_registry[APP_ID_DASHBOARDS].id},
                SHELL_MODE_PHOTOS: {"app_id": app_registry[APP_ID_PHOTOS].id},
                SHELL_MODE_NIGHT: {"app_id": night_app.id},
            },
        },
    }


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


def resolve_preview_asset_path(path_like: str) -> Path:
    preview_path = Path(path_like)
    if not preview_path.is_absolute():
        preview_path = BASE_DIR / preview_path
    return preview_path


def _measure_text(draw: ImageDraw.ImageDraw, text: str) -> tuple[int, int]:
    if hasattr(draw, "textbbox"):
        left, top, right, bottom = draw.textbbox((0, 0), text)
        return right - left, bottom - top
    return draw.textsize(text)


def menu_content_bounds(screen_height: int) -> tuple[int, int, int]:
    content_top = MENU_HEADER_HEIGHT
    footer_top = max(MENU_HEADER_HEIGHT + 1, screen_height - MENU_FOOTER_HEIGHT)
    content_bottom = max(content_top, footer_top - 1)
    return content_top, content_bottom, footer_top



def _make_region(action: str, left: int, top: int, right: int, bottom: int) -> TouchRegion:
    return TouchRegion(action=action, left=left, top=top, right=right, bottom=bottom)


def menu_touch_regions(menu_page: MenuPage, screen_width: int, screen_height: int) -> list[TouchRegion]:
    content_top, content_bottom, footer_top = menu_content_bounds(screen_height)
    mid_x = screen_width // 2
    mid_y = content_top + ((content_bottom - content_top + 1) // 2)
    actions = list(menu_page.tile_app_ids) + [None] * MENU_TILES_PER_PAGE
    regions = [
        _make_region(MENU_ACTION_NOOP, 0, 0, max(0, screen_width - 1), max(0, content_top - 1)),
        _make_region(actions[0] or MENU_ACTION_NOOP, 0, content_top, max(0, mid_x - 1), max(0, mid_y - 1)),
        _make_region(actions[1] or MENU_ACTION_NOOP, mid_x, content_top, max(0, screen_width - 1), max(0, mid_y - 1)),
        _make_region(actions[2] or MENU_ACTION_NOOP, 0, mid_y, max(0, mid_x - 1), max(0, content_bottom)),
        _make_region(actions[3] or MENU_ACTION_NOOP, mid_x, mid_y, max(0, screen_width - 1), max(0, content_bottom)),
    ]
    if menu_page.page_count <= 1:
        regions.append(_make_region(MENU_ACTION_NOOP, 0, footer_top, max(0, screen_width - 1), max(0, screen_height - 1)))
        return regions

    nav_width = max(56, min(84, screen_width // 5))
    left_nav_right = max(0, nav_width - 1)
    right_nav_left = max(0, screen_width - nav_width)
    center_left = min(screen_width - 1, left_nav_right + 1)
    center_right = max(center_left, right_nav_left - 1)
    regions.extend(
        [
            _make_region(MENU_ACTION_PREV_PAGE, 0, footer_top, left_nav_right, max(0, screen_height - 1)),
            _make_region(MENU_ACTION_NOOP, center_left, footer_top, center_right, max(0, screen_height - 1)),
            _make_region(MENU_ACTION_NEXT_PAGE, right_nav_left, footer_top, max(0, screen_width - 1), max(0, screen_height - 1)),
        ]
    )
    return regions


def _tile_boxes(screen_width: int, screen_height: int) -> list[tuple[int, int, int, int]]:
    content_top, content_bottom, _footer_top = menu_content_bounds(screen_height)
    grid_left = MENU_MARGIN
    grid_right = max(grid_left, screen_width - MENU_MARGIN - 1)
    grid_top = content_top + MENU_MARGIN
    grid_bottom = max(grid_top, content_bottom - MENU_MARGIN)
    total_width = max(2, grid_right - grid_left + 1)
    total_height = max(2, grid_bottom - grid_top + 1)
    tile_width = max(1, (total_width - MENU_GAP) // 2)
    tile_height = max(1, (total_height - MENU_GAP) // 2)
    right_column_left = min(grid_right, grid_left + tile_width + MENU_GAP)
    bottom_row_top = min(grid_bottom, grid_top + tile_height + MENU_GAP)
    return [
        (grid_left, grid_top, max(grid_left, right_column_left - MENU_GAP - 1), max(grid_top, bottom_row_top - MENU_GAP - 1)),
        (right_column_left, grid_top, grid_right, max(grid_top, bottom_row_top - MENU_GAP - 1)),
        (grid_left, bottom_row_top, max(grid_left, right_column_left - MENU_GAP - 1), grid_bottom),
        (right_column_left, bottom_row_top, grid_right, grid_bottom),
    ]


def _tile_preview_box(tile_box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = tile_box
    label_height = 22
    return (
        left + 6,
        top + 6,
        max(left + 6, right - 6),
        max(top + 6, bottom - label_height),
    )


def _draw_centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fill: tuple[int, int, int]) -> None:
    left, top, right, bottom = box
    text_width, text_height = _measure_text(draw, text)
    text_x = left + max(0, ((right - left + 1) - text_width) // 2)
    text_y = top + max(0, ((bottom - top + 1) - text_height) // 2)
    draw.text((text_x, text_y), text, fill=fill)


def render_menu_page(
    menu_page: MenuPage,
    app_registry: dict[str, AppSpec],
    screen_width: int,
    screen_height: int,
    *,
    show_touch_zones: bool,
) -> Image.Image:
    menu_image = Image.new("RGB", (screen_width, screen_height), MENU_BACKGROUND_TOP_RGB)
    draw = ImageDraw.Draw(menu_image)
    for row in range(screen_height):
        ratio = row / max(1, screen_height - 1)
        colour = tuple(
            int(MENU_BACKGROUND_TOP_RGB[channel] + ((MENU_BACKGROUND_BOTTOM_RGB[channel] - MENU_BACKGROUND_TOP_RGB[channel]) * ratio))
            for channel in range(3)
        )
        draw.line((0, row, screen_width, row), fill=colour)

    title = "zero2dash apps"
    page_label = f"Page {menu_page.page_index + 1}/{menu_page.page_count}"
    _draw_centered_text(draw, (0, 2, max(0, screen_width - 1), MENU_HEADER_HEIGHT - 1), title, MENU_TEXT_RGB)
    page_width, _page_height = _measure_text(draw, page_label)
    draw.text((max(4, screen_width - page_width - 8), 4), page_label, fill=MENU_SUBTLE_TEXT_RGB)

    for tile_index, tile_box in enumerate(_tile_boxes(screen_width, screen_height)):
        app_id = menu_page.tile_app_ids[tile_index]
        draw.rectangle(tile_box, fill=MENU_TILE_FILL_RGB, outline=MENU_TILE_OUTLINE_RGB, width=2)
        if app_id is None:
            _draw_centered_text(draw, tile_box, "Unused", MENU_SUBTLE_TEXT_RGB)
            continue

        app = app_registry[app_id]
        preview_left, preview_top, preview_right, preview_bottom = _tile_preview_box(tile_box)
        preview = load_selector_image(
            resolve_preview_asset_path(app.preview_asset),
            max(1, preview_right - preview_left + 1),
            max(1, preview_bottom - preview_top + 1),
        )
        menu_image.paste(preview, (preview_left, preview_top))
        draw.rectangle(tile_box, outline=MENU_ACCENT_RGB, width=1)
        left, _top, right, bottom = tile_box
        _draw_centered_text(draw, (left + 4, bottom - 22, right - 4, bottom - 4), app.label, MENU_TEXT_RGB)

    content_top, _content_bottom, footer_top = menu_content_bounds(screen_height)
    draw.line((0, content_top, screen_width, content_top), fill=(48, 70, 96), width=1)
    draw.line((0, footer_top, screen_width, footer_top), fill=(48, 70, 96), width=1)
    if menu_page.page_count > 1:
        _draw_centered_text(draw, (0, footer_top, 71, screen_height - 1), "< Prev", MENU_TEXT_RGB)
        _draw_centered_text(draw, (screen_width - 72, footer_top, screen_width - 1, screen_height - 1), "Next >", MENU_TEXT_RGB)
        _draw_centered_text(draw, (72, footer_top, max(72, screen_width - 73), screen_height - 1), "tap arrows to change page", MENU_SUBTLE_TEXT_RGB)
    else:
        _draw_centered_text(draw, (0, footer_top, max(0, screen_width - 1), screen_height - 1), "tap a tile to open", MENU_SUBTLE_TEXT_RGB)

    if show_touch_zones:
        menu_image = annotate_touch_regions(
            menu_image,
            menu_touch_regions(menu_page, screen_width, screen_height),
            f"Menu page {menu_page.page_index + 1}",
        )
    return menu_image


def build_menu_pages(
    app_registry: dict[str, AppSpec],
    screen_width: int,
    screen_height: int,
    *,
    show_touch_zones: bool,
) -> list[MenuPage]:
    ordered_apps = sorted(app_registry.values(), key=lambda app: (app.menu_page, app.tile_index, app.id))
    page_count = max((app.menu_page for app in ordered_apps), default=0) + 1
    menu_pages: list[MenuPage] = []
    for page_index in range(page_count):
        tile_app_ids: list[str | None] = [None] * MENU_TILES_PER_PAGE
        for app in ordered_apps:
            if app.menu_page != page_index:
                continue
            if 0 <= app.tile_index < MENU_TILES_PER_PAGE:
                tile_app_ids[app.tile_index] = app.id
        page_stub = MenuPage(
            page_index=page_index,
            page_count=page_count,
            tile_app_ids=tuple(tile_app_ids),
            image=Image.new("RGB", (screen_width, screen_height), BACKGROUND_RGB),
        )
        page_image = render_menu_page(page_stub, app_registry, screen_width, screen_height, show_touch_zones=show_touch_zones)
        menu_pages.append(
            MenuPage(
                page_index=page_index,
                page_count=page_count,
                tile_app_ids=tuple(tile_app_ids),
                image=page_image,
            )
        )
    return menu_pages


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


def resolve_menu_action(menu_page: MenuPage, screen_x: int, screen_y: int, screen_width: int, screen_height: int) -> str:
    return resolve_touch_region(screen_x, screen_y, menu_touch_regions(menu_page, screen_width, screen_height), "app menu")


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
        self.home_hold_started_at: float | None = None
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

    def _current_screen_position(self) -> tuple[int, int]:
        if self.device is None:
            return 0, 0
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

    def _commit_tap(self, now: float, ready_after: float, touch_debounce_secs: float, resolver) -> str | None:
        if self.device is None:
            return None
        if now < ready_after or (now - self.last_emit) < touch_debounce_secs:
            return None
        self.last_emit = now
        screen_x, screen_y = self._current_screen_position()
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

    def wait_for_home_gesture(self, home_region: TouchRegion, hold_secs: float, timeout_secs: float) -> bool:
        if self.handle is None or self.device is None:
            time.sleep(max(0.0, timeout_secs))
            return False
        deadline = time.monotonic() + max(0.0, timeout_secs)
        while not STOP_REQUESTED:
            now = time.monotonic()
            if self.touch_down:
                screen_x, screen_y = self._current_screen_position()
                if home_region.contains(screen_x, screen_y):
                    if self.home_hold_started_at is None:
                        self.home_hold_started_at = now
                    elif now - self.home_hold_started_at >= hold_secs:
                        print(
                            f"[boot-selector] Home gesture detected at screen_x={screen_x}, screen_y={screen_y}.",
                            flush=True,
                        )
                        self.home_hold_started_at = None
                        self.last_emit = now
                        return True
                else:
                    self.home_hold_started_at = None
            else:
                self.home_hold_started_at = None
            remaining = deadline - now
            if remaining <= 0:
                return False
            readable, _, _ = select.select([self.handle], [], [], min(0.05, remaining))
            if not readable:
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
                elif ev_value == 0:
                    self.touch_down = False
                    self.home_hold_started_at = None
            elif ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
                if ev_value == -1:
                    self.touch_down = False
                    self.home_hold_started_at = None
                elif ev_value >= 0:
                    self.touch_down = True
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


def wait_for_action(
    touch_reader: TouchReader,
    label: str,
    resolver,
    touch_settle_secs: float,
    touch_debounce_secs: float,
    timeout_secs: float | None = None,
) -> str | None:
    if not touch_reader.is_available():
        print("[boot-selector] No touch device found; touch controls disabled.", flush=True)
        return None
    print(f"[boot-selector] Waiting for {label} on {touch_reader.describe()}.", flush=True)
    ready_after = time.monotonic() + max(0.0, touch_settle_secs)
    return touch_reader.read_action(resolver, ready_after, touch_debounce_secs, timeout_secs=timeout_secs)


def wait_for_shell_action_or_mode(
    touch_reader: TouchReader,
    label: str,
    resolver,
    touch_settle_secs: float,
    touch_debounce_secs: float,
    mode_store: ModeSwitchRequestStore,
) -> tuple[str | None, str | None]:
    ready_after = time.monotonic() + max(0.0, touch_settle_secs)
    announced = False
    while not STOP_REQUESTED:
        requested_mode = mode_store.consume_request()
        if requested_mode is not None:
            return None, requested_mode
        if not touch_reader.is_available():
            if not announced:
                print("[boot-selector] No touch device found; waiting for shell mode requests only.", flush=True)
                announced = True
            time.sleep(POLL_TIMEOUT_SECS)
            continue
        if not announced:
            print(f"[boot-selector] Waiting for {label} on {touch_reader.describe()}.", flush=True)
            announced = True
        action = touch_reader.read_action(resolver, ready_after, touch_debounce_secs, timeout_secs=POLL_TIMEOUT_SECS)
        if action is not None:
            return action, None
    return None, None


def home_gesture_region(screen_width: int, screen_height: int, corner_width: int, corner_height: int) -> TouchRegion:
    return TouchRegion(
        action=SHELL_MODE_MENU,
        left=0,
        top=0,
        right=max(0, min(screen_width, corner_width) - 1),
        bottom=max(0, min(screen_height, corner_height) - 1),
    )


def wait_for_running_app_event(
    child_manager: ChildAppManager,
    touch_reader: TouchReader,
    mode_store: ModeSwitchRequestStore,
    home_region: TouchRegion,
    home_hold_secs: float,
) -> str:
    while not STOP_REQUESTED:
        requested_mode = mode_store.consume_request()
        if requested_mode is not None:
            return requested_mode
        running = child_manager.running_app()
        if running is None:
            return SHELL_MODE_MENU
        if running.app.supports_home_gesture and touch_reader.wait_for_home_gesture(home_region, home_hold_secs, POLL_TIMEOUT_SECS):
            return SHELL_MODE_MENU
        if not touch_reader.is_available() or not running.app.supports_home_gesture:
            time.sleep(POLL_TIMEOUT_SECS)
    return SHELL_MODE_MENU


def handle_mode_request(
    requested_mode: str,
    app_registry: dict[str, AppSpec],
    night_app: AppSpec,
    child_manager: ChildAppManager,
) -> str:
    if requested_mode == SHELL_MODE_MENU:
        child_manager.stop_current(reason="menu mode request")
        return SHELL_STATE_MAIN_MENU
    if requested_mode == SHELL_MODE_DASHBOARDS:
        if child_manager.start_app(app_registry[APP_ID_DASHBOARDS]):
            return SHELL_STATE_RUNNING_APP
        return SHELL_STATE_MAIN_MENU
    if requested_mode == SHELL_MODE_PHOTOS:
        if child_manager.start_app(app_registry[APP_ID_PHOTOS]):
            return SHELL_STATE_RUNNING_APP
        return SHELL_STATE_MAIN_MENU
    if requested_mode == SHELL_MODE_NIGHT:
        if child_manager.start_app(night_app):
            return SHELL_STATE_RUNNING_APP
        return SHELL_STATE_MAIN_MENU
    return SHELL_STATE_MAIN_MENU


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

def main() -> int:
    args = parse_args()
    validation_error = validate_args(args)
    if validation_error is not None:
        return validation_error

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    mode_store = ModeSwitchRequestStore(args.mode_request_path)

    if args.request_mode:
        mode_store.write_request(args.request_mode)
        print(f"[boot-selector] Wrote shell mode request {args.request_mode} to {mode_store.path}", flush=True)
        return 0

    app_registry = build_app_registry(args)
    night_app = build_night_mode_app(args)

    if args.dump_contracts:
        snapshot = build_contract_snapshot(app_registry, night_app, str(mode_store.path), args)
        print(json.dumps(snapshot, indent=2), flush=True)
        return 0

    if args.probe_touch:
        return run_touch_probe(args.width, args.height)

    menu_pages = build_menu_pages(
        app_registry,
        args.width,
        args.height,
        show_touch_zones=args.show_touch_zones,
    )
    shutdown_image = load_selector_image(Path(args.shutdown_image), args.width, args.height)
    keypad_image = load_selector_image(Path(args.keypad_image), args.width, args.height)
    shutdown_regions_map = vertical_regions(args.width, args.height, args.invert_y, SHUTDOWN_CONFIRM, SHUTDOWN_CANCEL)
    keypad_regions_map = keypad_regions(args.width, args.height)
    if args.show_touch_zones:
        for menu_page in menu_pages:
            log_touch_regions(f"menu page {menu_page.page_index + 1}", menu_touch_regions(menu_page, args.width, args.height))
        log_touch_regions("shutdown", shutdown_regions_map)
        log_touch_regions("keypad", keypad_regions_map)
        shutdown_image = annotate_touch_regions(shutdown_image, shutdown_regions_map, "Shutdown zones")
        keypad_image = annotate_touch_regions(keypad_image, keypad_regions_map, "Keypad zones")
    shell_images = ShellImages(
        menu_pages=tuple(menu_page.image for menu_page in menu_pages),
        shutdown=shutdown_image,
        keypad=keypad_image,
        blank=Image.new("RGB", (args.width, args.height), BACKGROUND_RGB),
    )
    save_preview(menu_pages[0].image, args.output_selector)

    framebuffer = None
    if not args.no_framebuffer:
        if not Path(args.fbdev).exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        framebuffer = FramebufferWriter(args.fbdev, args.width, args.height)
        framebuffer.open()

    touch_reader = TouchReader(args.width, args.height)
    child_manager = ChildAppManager(args.child_stop_grace_secs)
    home_region = home_gesture_region(
        args.width,
        args.height,
        args.home_gesture_corner_width,
        args.home_gesture_corner_height,
    )
    consecutive_pin_failures = 0
    current_menu_page = 0
    shell_state = SHELL_STATE_BOOT_GIF
    try:
        if not args.skip_gif:
            playback_gif(framebuffer, Path(args.gif), args.width, args.height, args.gif_speed, args.output_gif_first, args.output_gif_last)
        shell_state = SHELL_STATE_MAIN_MENU

        if args.no_framebuffer:
            print("Skipping touch loop because --no-framebuffer was set.", flush=True)
            return 0

        requested_mode = mode_store.consume_request()
        if requested_mode is not None:
            if requested_mode == SHELL_MODE_DASHBOARDS:
                current_menu_page = app_registry[APP_ID_DASHBOARDS].menu_page
            elif requested_mode == SHELL_MODE_PHOTOS:
                current_menu_page = app_registry[APP_ID_PHOTOS].menu_page
            shell_state = handle_mode_request(requested_mode, app_registry, night_app, child_manager)

        while not STOP_REQUESTED:
            if shell_state == SHELL_STATE_RUNNING_APP:
                next_mode = wait_for_running_app_event(
                    child_manager,
                    touch_reader,
                    mode_store,
                    home_region,
                    args.home_gesture_hold_secs,
                )
                shell_state = handle_mode_request(next_mode, app_registry, night_app, child_manager)
                continue

            if shell_state == SHELL_STATE_MAIN_MENU:
                if framebuffer is not None:
                    framebuffer.write_image(shell_images.menu_pages[current_menu_page])
                current_page = menu_pages[current_menu_page]
                main_action, requested_mode = wait_for_shell_action_or_mode(
                    touch_reader,
                    f"app menu selection (page {current_menu_page + 1}/{len(menu_pages)})",
                    lambda screen_x, screen_y: resolve_menu_action(current_page, screen_x, screen_y, args.width, args.height),
                    args.touch_settle_secs,
                    args.touch_debounce_secs,
                    mode_store,
                )
                if requested_mode is not None:
                    if requested_mode == SHELL_MODE_DASHBOARDS:
                        current_menu_page = app_registry[APP_ID_DASHBOARDS].menu_page
                    elif requested_mode == SHELL_MODE_PHOTOS:
                        current_menu_page = app_registry[APP_ID_PHOTOS].menu_page
                    shell_state = handle_mode_request(requested_mode, app_registry, night_app, child_manager)
                    continue
                if main_action == MENU_ACTION_PREV_PAGE:
                    current_menu_page = (current_menu_page - 1) % len(menu_pages)
                    continue
                if main_action == MENU_ACTION_NEXT_PAGE:
                    current_menu_page = (current_menu_page + 1) % len(menu_pages)
                    continue
                if main_action in {None, MENU_ACTION_NOOP}:
                    continue
                selected_app = app_registry.get(main_action)
                if selected_app is None:
                    continue
                current_menu_page = selected_app.menu_page
                if selected_app.id == APP_ID_DASHBOARDS:
                    if child_manager.start_app(selected_app):
                        shell_state = SHELL_STATE_RUNNING_APP
                    continue
                if selected_app.id == APP_ID_PHOTOS:
                    if child_manager.start_app(selected_app):
                        shell_state = SHELL_STATE_RUNNING_APP
                    continue
                if selected_app.id == APP_ID_INFO:
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
                    shell_state = SHELL_STATE_MAIN_MENU
                    continue
                if selected_app.id == APP_ID_KEYPAD:
                    shell_state = SHELL_STATE_KEYPAD
                    continue
                if selected_app.id == APP_ID_SHUTDOWN:
                    shell_state = SHELL_STATE_SHUTDOWN_CONFIRM
                    continue
                continue

            if shell_state == SHELL_STATE_KEYPAD:
                entered_pin = ""
                while not STOP_REQUESTED and shell_state == SHELL_STATE_KEYPAD:
                    if framebuffer is not None:
                        framebuffer.write_image(shell_images.keypad)
                    keypad_action, requested_mode = wait_for_shell_action_or_mode(
                        touch_reader,
                        "keypad selection",
                        lambda screen_x, screen_y: resolve_keypad_action(screen_x, screen_y, args.width, args.height),
                        args.touch_settle_secs,
                        args.touch_debounce_secs,
                        mode_store,
                    )
                    if requested_mode is not None:
                        shell_state = handle_mode_request(requested_mode, app_registry, night_app, child_manager)
                        break
                    if keypad_action in KEYPAD_DIGITS:
                        entered_pin += keypad_action
                        continue
                    if keypad_action == KEYPAD_NO:
                        shell_state = SHELL_STATE_MAIN_MENU
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
                            run_player(args.player_command)
                            shell_state = SHELL_STATE_MAIN_MENU
                            break
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
                            shell_state = SHELL_STATE_MAIN_MENU
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
                            child_manager.shutdown()
                            return run_shutdown(args.shutdown_command)
                    if keypad_action is None:
                        continue
                    shell_state = SHELL_STATE_MAIN_MENU
                continue

            if shell_state == SHELL_STATE_SHUTDOWN_CONFIRM:
                if framebuffer is not None:
                    framebuffer.write_image(shell_images.shutdown)
                shutdown_action, requested_mode = wait_for_shell_action_or_mode(
                    touch_reader,
                    "shutdown confirmation",
                    lambda _screen_x, screen_y: resolve_shutdown_action(screen_y, args.height, args.invert_y),
                    args.touch_settle_secs,
                    args.touch_debounce_secs,
                    mode_store,
                )
                if requested_mode is not None:
                    shell_state = handle_mode_request(requested_mode, app_registry, night_app, child_manager)
                    continue
                if shutdown_action == SHUTDOWN_CONFIRM:
                    child_manager.shutdown()
                    if framebuffer is not None:
                        framebuffer.write_image(shell_images.blank)
                    return run_shutdown(args.shutdown_command)
                if shutdown_action == SHUTDOWN_CANCEL:
                    shell_state = SHELL_STATE_MAIN_MENU
                    continue
                shell_state = SHELL_STATE_MAIN_MENU
                continue

            shell_state = SHELL_STATE_MAIN_MENU
        return 1 if STOP_REQUESTED else 0
    finally:
        child_manager.shutdown()
        touch_reader.close()
        if framebuffer is not None:
            framebuffer.close()


if __name__ == "__main__":
    raise SystemExit(main())
