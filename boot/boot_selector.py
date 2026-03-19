#!/usr/bin/env python3
"""Boot-time framebuffer shell with a theme-backed touch menu."""

from __future__ import annotations

import argparse
import json
import os
import select
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PIL import Image, ImageDraw, ImageFont, ImageSequence

import touch_calibration
from framebuffer import FramebufferWriter
from rotator.touch import (
    ABS_MT_POSITION_X,
    ABS_MT_POSITION_Y,
    ABS_MT_TRACKING_ID,
    ABS_X,
    ABS_Y,
    BTN_TOUCH,
    EV_ABS,
    EV_KEY,
    INPUT_EVENT_STRUCT,
    detect_touch_width,
    touch_probe,
)


FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
BOOT_DIR = BASE_DIR / "boot"
THEMES_DIR = BASE_DIR / "themes"

DEFAULT_STARTUP_GIF_PATH = os.environ.get("BOOT_SELECTOR_GIF_PATH", str(BOOT_DIR / "startup.gif"))
DEFAULT_CREDITS_GIF_PATH = os.environ.get("BOOT_SELECTOR_INFO_GIF", str(BOOT_DIR / "credits.gif"))
DEFAULT_SHUTDOWN_COMMAND = os.environ.get("BOOT_SELECTOR_SHUTDOWN_COMMAND", "systemctl poweroff")
DEFAULT_PLAYER_COMMAND = os.environ.get("BOOT_SELECTOR_PLAYER_COMMAND", "/home/pihole/zero2dash/player.sh")
DEFAULT_PIN = os.environ.get("BOOT_SELECTOR_PIN", "")
DEFAULT_DAY_SERVICE = os.environ.get("BOOT_SELECTOR_DAY_SERVICE", "display.service")
DEFAULT_NIGHT_SERVICE = os.environ.get("BOOT_SELECTOR_NIGHT_SERVICE", "night.service")
DEFAULT_TOUCH_SETTLE_SECS = float(os.environ.get("BOOT_SELECTOR_TOUCH_SETTLE_SECS", "0.35"))
DEFAULT_TOUCH_DEBOUNCE_SECS = float(os.environ.get("BOOT_SELECTOR_TOUCH_DEBOUNCE_SECS", "0.35"))
DEFAULT_GIF_SPEED = float(os.environ.get("BOOT_SELECTOR_GIF_SPEED", "0.5"))
DEFAULT_TOUCH_INVERT_Y = os.environ.get("BOOT_SELECTOR_TOUCH_INVERT_Y", "0").strip().lower() not in {"0", "false", "no", "off"}
DEFAULT_CHILD_STOP_GRACE_SECS = float(os.environ.get("BOOT_SELECTOR_CHILD_STOP_GRACE_SECS", "3.0"))
DEFAULT_HOME_GESTURE_HOLD_SECS = float(os.environ.get("BOOT_SELECTOR_HOME_GESTURE_HOLD_SECS", "1.5"))
DEFAULT_HOME_GESTURE_CORNER_WIDTH = int(os.environ.get("BOOT_SELECTOR_HOME_GESTURE_CORNER_WIDTH", "64"))
DEFAULT_HOME_GESTURE_CORNER_HEIGHT = int(os.environ.get("BOOT_SELECTOR_HOME_GESTURE_CORNER_HEIGHT", "48"))
DEFAULT_MODE_REQUEST_PATH = os.environ.get("BOOT_SELECTOR_MODE_REQUEST_PATH", str(Path(tempfile.gettempdir()) / "zero2dash-shell-mode-request"))
DEFAULT_THEME_ROOT = Path(os.environ.get("BOOT_SELECTOR_THEME_ROOT", str(THEMES_DIR)))
DEFAULT_THEME_ID = os.environ.get("BOOT_SELECTOR_DEFAULT_THEME", "default")
DEFAULT_SHOW_TOUCH_ZONES = os.environ.get("BOOT_SELECTOR_SHOW_TOUCH_ZONES", "0").strip().lower() not in {"0", "false", "no", "off"}

POLL_TIMEOUT_SECS = 0.2
MENU_STRIP_WIDTH = 20
THEME_PICKER_COLUMNS = ("default", "steele", "comic")

ROOT_MENU_1 = "main_menu_1"
ROOT_MENU_2 = "main_menu_2"
DASHBOARDS_MENU = "dashboards_menu"
SETTINGS_MENU = "settings_menu"
SHUTDOWN_CONFIRM = "shutdown_confirm"
PIN_KEYPAD = "pin_keypad"
THEMES_MENU = "themes_menu"
NETWORK_STATUS = "network_status"
PI_STATS_STATUS = "pi_stats_status"
LOGS_STATUS = "logs_status"
ISS_PLACEHOLDER = "iss_placeholder"
CREDITS_SCREEN = "credits"
ACCESS_GRANTED = "access_granted"
ACCESS_DENIED = "access_denied"
RUNNING_APP = "running_app"

SHELL_MODE_MENU = "menu"
SHELL_MODE_DASHBOARDS = "dashboards"
SHELL_MODE_PHOTOS = "photos"
SHELL_MODE_NIGHT = "night"
SHELL_MODES = (SHELL_MODE_MENU, SHELL_MODE_DASHBOARDS, SHELL_MODE_PHOTOS, SHELL_MODE_NIGHT)

APP_KIND_CHILD_PROCESS = "child_process"
APP_KIND_SHELL_SCREEN = "shell_screen"
APP_ID_DASHBOARDS = "dashboards"
APP_ID_PHOTOS = "photos"
APP_ID_NIGHT = "night"
APP_ID_CREDITS = "credits"
APP_ID_THEMES = "themes"
APP_ID_SETTINGS = "settings"
APP_ID_SHUTDOWN = "shutdown"
APP_ID_LOCKED_CONTENT = "locked_content"
APP_ID_NETWORK = "network"
APP_ID_PI_STATS = "pi_stats"
APP_ID_LOGS = "logs"
APP_ID_ISS = "iss"

THEME_IMAGE_FILES = {
    ROOT_MENU_1: "mainmenu1.png",
    ROOT_MENU_2: "mainmenu2.png",
    DASHBOARDS_MENU: "day-night.png",
    SETTINGS_MENU: "settings.png",
    SHUTDOWN_CONFIRM: "yes-no.png",
    PIN_KEYPAD: "keypad.png",
    THEMES_MENU: "themes.png",
    NETWORK_STATUS: "stats.png",
    PI_STATS_STATUS: "stats.png",
    LOGS_STATUS: "stats.png",
    ISS_PLACEHOLDER: "stats.png",
}
THEME_REQUIRED_FILES = set(THEME_IMAGE_FILES.values()) | {"granted.gif", "denied.gif"}

FG = (244, 247, 250)
ACCENT = (90, 180, 255)
WARN = (244, 198, 0)
BG = (0, 0, 0)
STOP_REQUESTED = False
RESAMPLING_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def _default_theme_state_path() -> Path:
    override = os.environ.get("BOOT_SELECTOR_THEME_STATE_PATH")
    if override:
        return Path(override)
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "zero2dash" / "shell-theme"
    return Path.home() / ".cache" / "zero2dash" / "shell-theme"


DEFAULT_THEME_STATE_PATH = _default_theme_state_path()


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
class ThemeAssets:
    theme_id: str
    root: Path
    assets: dict[str, Path]

    def asset(self, asset_name: str) -> Path:
        return self.assets[asset_name]


@dataclass(frozen=True)
class AppSpec:
    id: str
    label: str
    kind: str
    launch_command: tuple[str, ...]
    preview_asset: str
    supports_home_gesture: bool = False
    parent_screen: str | None = None

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "launch_command": list(self.launch_command),
            "preview_asset": self.preview_asset,
            "supports_home_gesture": self.supports_home_gesture,
            "parent_screen": self.parent_screen,
        }


@dataclass(frozen=True)
class ShellImages:
    screens: dict[str, Image.Image]
    status_base: Image.Image
    granted_gif: Path
    denied_gif: Path


@dataclass
class RunningChildApp:
    app: AppSpec
    process: subprocess.Popen[bytes] | subprocess.Popen[str]
    started_at: float


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


class ThemeStateStore:
    def __init__(self, path_like: str | Path) -> None:
        self.path = Path(path_like)

    def read_theme_id(self) -> str | None:
        try:
            payload = self.path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        except OSError as exc:
            print(f"[boot-selector] Failed to read theme state {self.path}: {exc}", file=sys.stderr, flush=True)
            return None
        return payload or None

    def write_theme_id(self, theme_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.{os.getpid()}.tmp")
        try:
            tmp_path.write_text(f"{theme_id}\n", encoding="utf-8")
            os.replace(tmp_path, self.path)
        except OSError as exc:
            print(f"[boot-selector] Failed to persist theme state {self.path}: {exc}", file=sys.stderr, flush=True)
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass


class ChildAppManager:
    def __init__(self, stop_grace_secs: float) -> None:
        self.stop_grace_secs = stop_grace_secs
        self._running: RunningChildApp | None = None

    def running_app(self) -> RunningChildApp | None:
        if self._running is None:
            return None
        if self._running.process.poll() is None:
            return self._running
        print(f"[boot-selector] Child app {self._running.app.id} exited with code {self._running.process.returncode}. Returning control to shell.", flush=True)
        self._running = None
        return None

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
            process = subprocess.Popen(list(app.launch_command), cwd=str(BASE_DIR))
        except OSError as exc:
            print(f"[boot-selector] Failed to start child app {app.id}: {exc}", file=sys.stderr, flush=True)
            return False
        self._running = RunningChildApp(app=app, process=process, started_at=time.monotonic())
        return True

    def stop_current(self, reason: str) -> bool:
        running = self.running_app()
        if running is None:
            return False
        print(f"[boot-selector] Stopping child app {running.app.id}: {reason}", flush=True)
        try:
            running.process.terminate()
        except ProcessLookupError:
            self._running = None
            return True
        try:
            running.process.wait(timeout=self.stop_grace_secs)
        except subprocess.TimeoutExpired:
            print(f"[boot-selector] Child app {running.app.id} did not exit after SIGTERM; forcing termination.", flush=True)
            running.process.kill()
            running.process.wait(timeout=2.0)
        self._running = None
        return True

    def shutdown(self) -> None:
        self.stop_current(reason="shell shutdown")


class TouchReader:
    def __init__(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.device, self.reason = touch_probe()
        self._fd = None
        self._touch_width = screen_width
        self._touch_min_x = 0
        self._use_calibration = bool(self.device and touch_calibration.applies_to(self.device))
        if self.device and not self._use_calibration:
            self._touch_width, self._touch_min_x = detect_touch_width(self.device, screen_width)

    def is_available(self) -> bool:
        return self.device is not None

    def describe(self) -> str:
        if not self.device:
            return "no touch device"
        return f"{self.device} ({self.reason})"

    def close(self) -> None:
        if self._fd is not None:
            try:
                self._fd.close()
            finally:
                self._fd = None

    def _ensure_open(self):
        if self.device is None:
            return None
        if self._fd is None:
            self._fd = open(self.device, "rb", buffering=0)
        return self._fd

    def _map_coordinates(self, raw_x: int, raw_y: int) -> tuple[int, int]:
        if self._use_calibration:
            return touch_calibration.map_to_screen(raw_x, raw_y, width=self.screen_width, height=self.screen_height)
        x = raw_x - self._touch_min_x
        if x < 0:
            x = 0
        elif x >= self._touch_width:
            x = self._touch_width - 1
        return min(self.screen_width - 1, max(0, x)), min(self.screen_height - 1, max(0, raw_y))

    def read_action(
        self,
        resolver: Callable[[int, int], str | None],
        ready_after: float,
        touch_debounce_secs: float,
        timeout_secs: float | None = None,
    ) -> str | None:
        if not self.is_available():
            return None
        fd = self._ensure_open()
        if fd is None:
            return None
        last_x = self.screen_width // 2
        last_y = self.screen_height // 2
        touch_down = False
        last_emit = 0.0
        deadline = None if timeout_secs is None else time.monotonic() + timeout_secs
        while not STOP_REQUESTED:
            wait_secs = 0.2 if deadline is None else max(0.0, min(0.2, deadline - time.monotonic()))
            if deadline is not None and wait_secs <= 0:
                return None
            readable, _, _ = select.select([fd], [], [], wait_secs)
            if not readable:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                continue
            raw = fd.read(INPUT_EVENT_STRUCT.size)
            if len(raw) != INPUT_EVENT_STRUCT.size:
                continue
            _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)
            if ev_type == EV_ABS and ev_code in (ABS_X, ABS_MT_POSITION_X):
                last_x = ev_value
                continue
            if ev_type == EV_ABS and ev_code in (ABS_Y, ABS_MT_POSITION_Y):
                last_y = ev_value
                continue
            if ev_type == EV_KEY and ev_code == BTN_TOUCH:
                if ev_value == 1:
                    touch_down = True
                elif ev_value == 0 and touch_down:
                    touch_down = False
                    now = time.monotonic()
                    if now < ready_after or (now - last_emit) < touch_debounce_secs:
                        continue
                    action = resolver(*self._map_coordinates(last_x, last_y))
                    if action is not None:
                        last_emit = now
                        return action
                continue
            if ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
                if ev_value >= 0:
                    touch_down = True
                elif touch_down:
                    touch_down = False
                    now = time.monotonic()
                    if now < ready_after or (now - last_emit) < touch_debounce_secs:
                        continue
                    action = resolver(*self._map_coordinates(last_x, last_y))
                    if action is not None:
                        last_emit = now
                        return action
        return None

    def wait_for_home_gesture(self, region: TouchRegion, hold_secs: float, poll_timeout_secs: float) -> bool:
        if not self.is_available():
            return False
        fd = self._ensure_open()
        if fd is None:
            return False
        touch_down = False
        touch_started_at = 0.0
        last_x = self.screen_width // 2
        last_y = self.screen_height // 2
        while not STOP_REQUESTED:
            readable, _, _ = select.select([fd], [], [], poll_timeout_secs)
            if not readable:
                if touch_down and region.contains(last_x, last_y) and (time.monotonic() - touch_started_at) >= hold_secs:
                    return True
                continue
            raw = fd.read(INPUT_EVENT_STRUCT.size)
            if len(raw) != INPUT_EVENT_STRUCT.size:
                continue
            _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)
            if ev_type == EV_ABS and ev_code in (ABS_X, ABS_MT_POSITION_X):
                last_x = ev_value
                continue
            if ev_type == EV_ABS and ev_code in (ABS_Y, ABS_MT_POSITION_Y):
                last_y = ev_value
                continue
            if ev_type == EV_KEY and ev_code == BTN_TOUCH:
                if ev_value == 1:
                    touch_down = True
                    touch_started_at = time.monotonic()
                elif ev_value == 0:
                    touch_down = False
                continue
            if ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
                if ev_value >= 0:
                    touch_down = True
                    touch_started_at = time.monotonic()
                elif ev_value == -1:
                    touch_down = False
        return False


def request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def shutdown_command_args(command_text: str) -> list[str]:
    return shlex.split(command_text)


def player_command_args(command_text: str) -> list[str]:
    return shlex.split(command_text)


def _command_for_service(service_name: str, fallback_command: list[str]) -> tuple[str, ...]:
    command_map = {
        "display.service": [sys.executable, "-u", str(BASE_DIR / "display_rotator.py")],
        "night.service": [sys.executable, "-u", str(BASE_DIR / "modules" / "blackout" / "blackout.py")],
    }
    command = command_map.get(service_name)
    if command is None:
        print(f"[boot-selector] No direct mapping is defined for {service_name}; using shell-owned fallback command {fallback_command}.", file=sys.stderr, flush=True)
        command = fallback_command
    return tuple(command)


def build_app_registry(args: argparse.Namespace) -> dict[str, AppSpec]:
    day_command = _command_for_service(args.day_service, [sys.executable, "-u", str(BASE_DIR / "display_rotator.py")])
    night_command = _command_for_service(args.night_service, [sys.executable, "-u", str(BASE_DIR / "modules" / "blackout" / "blackout.py")])
    return {
        APP_ID_DASHBOARDS: AppSpec(APP_ID_DASHBOARDS, "Dashboards", APP_KIND_CHILD_PROCESS, day_command, "day-night.png", True, ROOT_MENU_1),
        APP_ID_PHOTOS: AppSpec(APP_ID_PHOTOS, "Photos", APP_KIND_CHILD_PROCESS, (sys.executable, "-u", str(BASE_DIR / "modules" / "photos" / "slideshow.py")), "mainmenu1.png", True, ROOT_MENU_1),
        APP_ID_NIGHT: AppSpec(APP_ID_NIGHT, "Night", APP_KIND_CHILD_PROCESS, night_command, "day-night.png", True, DASHBOARDS_MENU),
        APP_ID_CREDITS: AppSpec(APP_ID_CREDITS, "Credits", APP_KIND_SHELL_SCREEN, (), "credits.gif", False, ROOT_MENU_2),
        APP_ID_THEMES: AppSpec(APP_ID_THEMES, "Themes", APP_KIND_SHELL_SCREEN, (), "themes.png", False, ROOT_MENU_2),
        APP_ID_SETTINGS: AppSpec(APP_ID_SETTINGS, "Settings", APP_KIND_SHELL_SCREEN, (), "settings.png", False, ROOT_MENU_2),
        APP_ID_SHUTDOWN: AppSpec(APP_ID_SHUTDOWN, "Shutdown", APP_KIND_SHELL_SCREEN, (), "yes-no.png", False, ROOT_MENU_2),
        APP_ID_LOCKED_CONTENT: AppSpec(APP_ID_LOCKED_CONTENT, "Locked Content", APP_KIND_SHELL_SCREEN, (), "keypad.png", False, ROOT_MENU_1),
        APP_ID_NETWORK: AppSpec(APP_ID_NETWORK, "Network", APP_KIND_SHELL_SCREEN, (), "stats.png", False, SETTINGS_MENU),
        APP_ID_PI_STATS: AppSpec(APP_ID_PI_STATS, "Pi Stats", APP_KIND_SHELL_SCREEN, (), "stats.png", False, SETTINGS_MENU),
        APP_ID_LOGS: AppSpec(APP_ID_LOGS, "Logs", APP_KIND_SHELL_SCREEN, (), "stats.png", False, SETTINGS_MENU),
        APP_ID_ISS: AppSpec(APP_ID_ISS, "NASA ISS", APP_KIND_SHELL_SCREEN, (), "stats.png", False, ROOT_MENU_1),
    }


def load_theme_catalog(theme_root: Path) -> dict[str, ThemeAssets]:
    if not theme_root.exists():
        raise RuntimeError(f"Theme root not found: {theme_root}")
    required_asset_names = sorted(THEME_REQUIRED_FILES)
    catalog: dict[str, ThemeAssets] = {}
    for theme_dir in sorted(path for path in theme_root.iterdir() if path.is_dir()):
        missing = [asset_name for asset_name in required_asset_names if not (theme_dir / asset_name).exists()]
        if missing:
            print(f"[boot-selector] Skipping theme {theme_dir.name}; missing assets: {', '.join(missing)}", file=sys.stderr, flush=True)
            continue
        catalog[theme_dir.name] = ThemeAssets(theme_dir.name, theme_dir, {asset_name: theme_dir / asset_name for asset_name in required_asset_names})
    if not catalog:
        raise RuntimeError(f"No valid themes found under {theme_root}")
    return catalog


def validate_theme_selection(theme_id: str, catalog: dict[str, ThemeAssets]) -> str:
    if theme_id in catalog:
        return theme_id
    if DEFAULT_THEME_ID in catalog:
        print(f"[boot-selector] Theme {theme_id!r} is unavailable; falling back to {DEFAULT_THEME_ID!r}.", file=sys.stderr, flush=True)
        return DEFAULT_THEME_ID
    return sorted(catalog)[0]


def load_theme_selection(theme_state_store: ThemeStateStore, catalog: dict[str, ThemeAssets], default_theme_id: str) -> str:
    saved = theme_state_store.read_theme_id()
    if saved in catalog:
        return saved  # type: ignore[return-value]
    if default_theme_id in catalog:
        return default_theme_id
    return sorted(catalog)[0]


def load_image(path: Path, width: int, height: int) -> Image.Image:
    return Image.open(path).convert("RGB").resize((width, height), RESAMPLING_LANCZOS)


def load_gif_frames(gif_path: Path, width: int, height: int, speed: float) -> list[tuple[Image.Image, float]]:
    frames: list[tuple[Image.Image, float]] = []
    with Image.open(gif_path) as gif:
        for frame in ImageSequence.Iterator(gif):
            duration = max(20, int(frame.info.get("duration", 100))) / 1000.0
            frames.append((frame.convert("RGB").resize((width, height), RESAMPLING_LANCZOS), duration / speed))
    return frames


def save_preview(image: Image.Image, output_path: str | None) -> None:
    if not output_path:
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    print(f"[boot-selector] Saved preview image to {path}", flush=True)


def build_shell_images(theme: ThemeAssets, width: int, height: int) -> ShellImages:
    screens = {screen_name: load_image(theme.asset(filename), width, height) for screen_name, filename in THEME_IMAGE_FILES.items()}
    return ShellImages(screens=screens, status_base=screens[NETWORK_STATUS], granted_gif=theme.asset("granted.gif"), denied_gif=theme.asset("denied.gif"))


def _screen_image(shell_images: ShellImages, screen_name: str) -> Image.Image:
    return shell_images.screens[screen_name]


def draw_status_screen(base_image: Image.Image, screen_name: str, status_text: str | None = None) -> Image.Image:
    frame = base_image.copy()
    draw = ImageDraw.Draw(frame)
    title_map = {NETWORK_STATUS: "Network", PI_STATS_STATUS: "Pi Stats", LOGS_STATUS: "Logs", ISS_PLACEHOLDER: "NASA ISS"}
    default_map = {NETWORK_STATUS: "Unavailable", PI_STATS_STATUS: "Unavailable", LOGS_STATUS: "Unavailable", ISS_PLACEHOLDER: "Placeholder only"}
    title = title_map.get(screen_name, screen_name.replace("_", " ").title())
    body = status_text or os.environ.get(f"BOOT_SELECTOR_{screen_name.upper()}_TEXT", "").strip() or default_map.get(screen_name, "Unavailable")
    font = ImageFont.load_default()
    draw.text((20, 18), title, font=font, fill=ACCENT)
    draw.text((20, 54), body, font=font, fill=WARN if body == "Unavailable" else FG)
    return frame


def annotate_touch_regions(image: Image.Image, regions: list[TouchRegion], title: str) -> Image.Image:
    frame = image.copy()
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, frame.width - 1, frame.height - 1), outline=ACCENT, width=1)
    draw.text((8, 4), title, font=ImageFont.load_default(), fill=ACCENT)
    for region in regions:
        draw.rectangle((region.left, region.top, region.right, region.bottom), outline=WARN, width=1)
    return frame


def root_strip_action(screen_name: str) -> str:
    return ROOT_MENU_2 if screen_name == ROOT_MENU_1 else ROOT_MENU_1


def resolve_shutdown_action(screen_y: int, screen_height: int, invert_y: bool) -> str:
    if invert_y:
        screen_y = screen_height - screen_y
    return "confirm" if screen_y < (screen_height // 2) else "cancel"


def resolve_theme_picker_action(screen_x: int, screen_y: int, screen_width: int, screen_height: int) -> str | None:
    _ = screen_y
    usable_width = max(1, screen_width - MENU_STRIP_WIDTH)
    column_width = usable_width / 3.0
    column = int((screen_x - MENU_STRIP_WIDTH) / column_width)
    if column < 0:
        column = 0
    if column > 2:
        column = 2
    return THEME_PICKER_COLUMNS[column]


def resolve_keypad_action(screen_x: int, screen_y: int, screen_width: int, screen_height: int) -> str | None:
    column = min(2, max(0, screen_x // max(1, screen_width // 3)))
    row = min(3, max(0, screen_y // max(1, screen_height // 4)))
    keypad = (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("cancel", "0", "ok"))
    return keypad[row][column]


def resolve_screen_action(screen_name: str, screen_x: int, screen_y: int, screen_width: int, screen_height: int) -> str | None:
    if screen_name in {ROOT_MENU_1, ROOT_MENU_2}:
        if screen_x < MENU_STRIP_WIDTH:
            return root_strip_action(screen_name)
        half_w = screen_width // 2
        half_h = screen_height // 2
        if screen_name == ROOT_MENU_1:
            if screen_x < half_w and screen_y < half_h:
                return "dashboards"
            if screen_x >= half_w and screen_y < half_h:
                return "photos"
            if screen_x < half_w and screen_y >= half_h:
                return "iss"
            return APP_ID_LOCKED_CONTENT
        if screen_x < half_w and screen_y < half_h:
            return "credits"
        if screen_x >= half_w and screen_y < half_h:
            return "themes"
        if screen_x < half_w and screen_y >= half_h:
            return "settings"
        return "shutdown"
    if screen_name == DASHBOARDS_MENU:
        if screen_x < MENU_STRIP_WIDTH:
            return ROOT_MENU_1
        return "dashboards" if screen_y < (screen_height // 2) else "night"
    if screen_name == SETTINGS_MENU:
        if screen_x < MENU_STRIP_WIDTH:
            return ROOT_MENU_2
        third = screen_height // 3
        if screen_y < third:
            return "network"
        if screen_y < third * 2:
            return "pi_stats"
        return "logs"
    if screen_name == SHUTDOWN_CONFIRM:
        if screen_x < MENU_STRIP_WIDTH:
            return "cancel"
        return resolve_shutdown_action(screen_y, screen_height, False)
    if screen_name == THEMES_MENU:
        if screen_x < MENU_STRIP_WIDTH:
            return ROOT_MENU_2
        return resolve_theme_picker_action(screen_x, screen_y, screen_width, screen_height)
    if screen_name == PIN_KEYPAD:
        return resolve_keypad_action(screen_x, screen_y, screen_width, screen_height)
    if screen_name in {NETWORK_STATUS, PI_STATS_STATUS, LOGS_STATUS}:
        return SETTINGS_MENU if screen_x < MENU_STRIP_WIDTH else None
    if screen_name == ISS_PLACEHOLDER:
        return ROOT_MENU_1 if screen_x < MENU_STRIP_WIDTH else None
    return None


def resolve_menu_action(menu_page, screen_x: int, screen_y: int, screen_width: int, screen_height: int) -> str | None:
    screen_name = getattr(menu_page, "screen_name", getattr(menu_page, "name", menu_page))
    return resolve_screen_action(screen_name, screen_x, screen_y, screen_width, screen_height)


def wait_for_action(
    touch_reader: "TouchReader",
    label: str,
    resolver: Callable[[int, int], str | None],
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
    touch_reader: "TouchReader",
    label: str,
    resolver: Callable[[int, int], str | None],
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
    return TouchRegion(SHELL_MODE_MENU, 0, 0, max(0, min(screen_width, corner_width) - 1), max(0, min(screen_height, corner_height) - 1))


def wait_for_running_app_event(
    child_manager: ChildAppManager,
    touch_reader: "TouchReader",
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


def evaluate_pin_entry(entered_pin: str, expected_pin: str, consecutive_failures: int) -> tuple[str, int]:
    if entered_pin == expected_pin:
        return "success", 0
    consecutive_failures += 1
    return ("shutdown", consecutive_failures) if consecutive_failures >= 3 else ("retry", consecutive_failures)


def run_shutdown(command_text: str) -> int:
    command = shutdown_command_args(command_text)
    if not command:
        print("[boot-selector] Shutdown command is empty.", file=sys.stderr, flush=True)
        return 1
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
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode == 0:
        print("[boot-selector] Player command completed successfully.", flush=True)
        return 0
    stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
    print(f"[boot-selector] Player command failed: {stderr}", file=sys.stderr, flush=True)
    return result.returncode


def handle_mode_request(requested_mode: str, app_registry: dict[str, AppSpec], night_app: AppSpec, child_manager: ChildAppManager) -> str:
    if requested_mode == SHELL_MODE_MENU:
        child_manager.stop_current(reason="menu mode request")
        return SHELL_MODE_MENU
    if requested_mode == SHELL_MODE_DASHBOARDS:
        return RUNNING_APP if child_manager.start_app(app_registry[APP_ID_DASHBOARDS]) else SHELL_MODE_MENU
    if requested_mode == SHELL_MODE_PHOTOS:
        return RUNNING_APP if child_manager.start_app(app_registry[APP_ID_PHOTOS]) else SHELL_MODE_MENU
    if requested_mode == SHELL_MODE_NIGHT:
        return RUNNING_APP if child_manager.start_app(night_app) else SHELL_MODE_MENU
    return SHELL_MODE_MENU


def build_contract_snapshot(
    app_registry: dict[str, AppSpec],
    night_app: AppSpec,
    mode_request_path: str,
    args: argparse.Namespace,
    theme_catalog: dict[str, ThemeAssets],
    active_theme_id: str,
) -> dict[str, object]:
    return {
        "shell_modes": list(SHELL_MODES),
        "mode_request_path": mode_request_path,
        "theme_root": args.theme_root,
        "default_theme": args.default_theme,
        "active_theme": active_theme_id,
        "themes": sorted(theme_catalog),
        "apps": {app_id: app.to_contract_dict() for app_id, app in app_registry.items()},
        "night_app": night_app.to_contract_dict(),
        "screens": [ROOT_MENU_1, ROOT_MENU_2, DASHBOARDS_MENU, SETTINGS_MENU, SHUTDOWN_CONFIRM, PIN_KEYPAD, THEMES_MENU, NETWORK_STATUS, PI_STATS_STATUS, LOGS_STATUS, ISS_PLACEHOLDER, CREDITS_SCREEN, ACCESS_GRANTED, ACCESS_DENIED],
    }


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play a boot GIF once, then show a theme-backed touch selector.")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
    parser.add_argument("--gif", default=DEFAULT_STARTUP_GIF_PATH, help=f"Startup GIF path (default: {DEFAULT_STARTUP_GIF_PATH})")
    parser.add_argument("--theme-root", default=str(DEFAULT_THEME_ROOT), help=f"Theme root directory (default: {DEFAULT_THEME_ROOT})")
    parser.add_argument("--default-theme", default=DEFAULT_THEME_ID, help=f"Default theme id (default: {DEFAULT_THEME_ID})")
    parser.add_argument("--theme-state-path", default=str(DEFAULT_THEME_STATE_PATH), help=f"Theme state file path (default: {DEFAULT_THEME_STATE_PATH})")
    parser.add_argument("--gif-speed", type=float, default=DEFAULT_GIF_SPEED, help=f"GIF playback speed multiplier (default: {DEFAULT_GIF_SPEED})")
    parser.add_argument("--invert-y", action="store_true", default=DEFAULT_TOUCH_INVERT_Y, help="Invert the touch Y axis when deciding top/bottom selection.")
    parser.add_argument("--no-invert-y", action="store_false", dest="invert_y", help="Disable Y-axis inversion for top/bottom selection.")
    parser.add_argument("--output-selector", help="Optional output path for the rendered startup selector screen.")
    parser.add_argument("--output-gif-first", help="Optional output path for the first rendered startup GIF frame.")
    parser.add_argument("--output-gif-last", help="Optional output path for the last rendered startup GIF frame.")
    parser.add_argument("--dump-contracts", action="store_true", help="Print the shell contracts as JSON and exit.")
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


def run_touch_probe(width: int) -> int:
    device, reason = touch_probe()
    if not device:
        print("[boot-selector] Touch probe found no usable device.", flush=True)
        print(f"[boot-selector] Probe reason: {reason}", flush=True)
        return 1
    touch_width, touch_min_x = detect_touch_width(device, width)
    print(f"[boot-selector] Touch probe selected {device}", flush=True)
    print(f"[boot-selector] Probe reason: {reason}", flush=True)
    print(f"[boot-selector] Probe width calibration: width={touch_width} min_x={touch_min_x}", flush=True)
    return 0


def playback_gif(
    framebuffer: FramebufferWriter | None,
    gif_path: Path,
    width: int,
    height: int,
    speed: float,
    output_first: str | None,
    output_last: str | None,
    *,
    touch_reader: TouchReader | None = None,
    touch_settle_secs: float = 0.0,
    touch_debounce_secs: float = 0.0,
    skip_action: str | None = None,
) -> str | None:
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
        return skip_action
    ready_after = time.monotonic() + max(0.0, touch_settle_secs)
    resolver = (lambda _screen_x, _screen_y: skip_action) if skip_action is not None else None
    for frame, duration in frames:
        if STOP_REQUESTED:
            return None
        write_framebuffer_image(framebuffer, frame)
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


def write_framebuffer_image(framebuffer: FramebufferWriter, image: Image.Image) -> None:
    write_frame = getattr(framebuffer, "write_frame", None)
    if callable(write_frame):
        write_frame(image)
        return
    write_image = getattr(framebuffer, "write_image", None)
    if callable(write_image):
        write_image(image)
        return
    raise AttributeError("Framebuffer object does not expose write_frame() or write_image()")


def run_main_screen_shell(
    args: argparse.Namespace,
    framebuffer: FramebufferWriter | None,
    touch_reader: TouchReader,
    mode_store: ModeSwitchRequestStore,
    app_registry: dict[str, AppSpec],
    theme_catalog: dict[str, ThemeAssets],
    theme_state_store: ThemeStateStore,
    shell_images: ShellImages,
    active_theme_id: str,
) -> int:
    child_manager = ChildAppManager(args.child_stop_grace_secs)
    home_region = home_gesture_region(args.width, args.height, args.home_gesture_corner_width, args.home_gesture_corner_height)
    current_screen = ROOT_MENU_1
    session_root_page = ROOT_MENU_1
    consecutive_pin_failures = 0
    entered_pin = ""
    pending_pin_shutdown = False

    requested_mode = mode_store.consume_request()
    if requested_mode is not None:
        current_screen = RUNNING_APP if handle_mode_request(requested_mode, app_registry, app_registry[APP_ID_NIGHT], child_manager) == RUNNING_APP else session_root_page

    while not STOP_REQUESTED:
        if child_manager.running_app() is not None:
            next_mode = wait_for_running_app_event(child_manager, touch_reader, mode_store, home_region, args.home_gesture_hold_secs)
            if next_mode == SHELL_MODE_MENU:
                child_manager.stop_current(reason="menu request")
                current_screen = session_root_page
                continue
            current_screen = RUNNING_APP if handle_mode_request(next_mode, app_registry, app_registry[APP_ID_NIGHT], child_manager) == RUNNING_APP else session_root_page
            continue

        if current_screen == CREDITS_SCREEN:
            playback_gif(
                framebuffer,
                Path(DEFAULT_CREDITS_GIF_PATH),
                args.width,
                args.height,
                args.gif_speed,
                None,
                None,
                touch_reader=touch_reader,
                touch_settle_secs=args.touch_settle_secs,
                touch_debounce_secs=args.touch_debounce_secs,
                skip_action="skip_credits",
            )
            current_screen = ROOT_MENU_2
            continue

        if current_screen == ACCESS_GRANTED:
            playback_gif(framebuffer, shell_images.granted_gif, args.width, args.height, args.gif_speed, None, None)
            run_player(args.player_command)
            current_screen = session_root_page
            continue

        if current_screen == ACCESS_DENIED:
            playback_gif(framebuffer, shell_images.denied_gif, args.width, args.height, args.gif_speed, None, None)
            if pending_pin_shutdown:
                child_manager.shutdown()
                if framebuffer is not None:
                    write_framebuffer_image(framebuffer, Image.new("RGB", (args.width, args.height), BG))
                return run_shutdown(args.shutdown_command)
            current_screen = session_root_page
            continue

        if current_screen in {NETWORK_STATUS, PI_STATS_STATUS, LOGS_STATUS, ISS_PLACEHOLDER}:
            if framebuffer is not None:
                write_framebuffer_image(framebuffer, draw_status_screen(shell_images.status_base, current_screen))
            action, requested_mode = wait_for_shell_action_or_mode(
                touch_reader,
                f"{current_screen} selection",
                lambda x, y: resolve_screen_action(current_screen, x, y, args.width, args.height),
                args.touch_settle_secs,
                args.touch_debounce_secs,
                mode_store,
            )
            if requested_mode is not None:
                if requested_mode == SHELL_MODE_MENU:
                    child_manager.stop_current(reason="menu mode request")
                    current_screen = session_root_page
                else:
                    current_screen = RUNNING_APP if handle_mode_request(requested_mode, app_registry, app_registry[APP_ID_NIGHT], child_manager) == RUNNING_APP else session_root_page
                continue
            if action is not None:
                current_screen = action
            continue

        if framebuffer is not None:
            write_framebuffer_image(framebuffer, _screen_image(shell_images, current_screen))
        action, requested_mode = wait_for_shell_action_or_mode(
            touch_reader,
            f"{current_screen} selection",
            lambda x, y: resolve_screen_action(current_screen, x, y, args.width, args.height),
            args.touch_settle_secs,
            args.touch_debounce_secs,
            mode_store,
        )
        if requested_mode is not None:
            if requested_mode == SHELL_MODE_MENU:
                child_manager.stop_current(reason="menu mode request")
                current_screen = session_root_page
            else:
                current_screen = RUNNING_APP if handle_mode_request(requested_mode, app_registry, app_registry[APP_ID_NIGHT], child_manager) == RUNNING_APP else session_root_page
            continue

        if current_screen == ROOT_MENU_1:
            if action == ROOT_MENU_2:
                session_root_page = ROOT_MENU_2
                current_screen = ROOT_MENU_2
            elif action == "dashboards":
                session_root_page = ROOT_MENU_1
                if child_manager.start_app(app_registry[APP_ID_DASHBOARDS]):
                    current_screen = RUNNING_APP
            elif action == "photos":
                session_root_page = ROOT_MENU_1
                if child_manager.start_app(app_registry[APP_ID_PHOTOS]):
                    current_screen = RUNNING_APP
            elif action == "iss":
                current_screen = ISS_PLACEHOLDER
            elif action == APP_ID_LOCKED_CONTENT:
                current_screen = PIN_KEYPAD
                entered_pin = ""
        elif current_screen == ROOT_MENU_2:
            if action == ROOT_MENU_1:
                session_root_page = ROOT_MENU_1
                current_screen = ROOT_MENU_1
            elif action == "credits":
                current_screen = CREDITS_SCREEN
            elif action == "themes":
                current_screen = THEMES_MENU
            elif action == "settings":
                current_screen = SETTINGS_MENU
            elif action == "shutdown":
                current_screen = SHUTDOWN_CONFIRM
        elif current_screen == DASHBOARDS_MENU:
            if action == ROOT_MENU_1:
                session_root_page = ROOT_MENU_1
                current_screen = ROOT_MENU_1
            elif action == "dashboards":
                if child_manager.start_app(app_registry[APP_ID_DASHBOARDS]):
                    current_screen = RUNNING_APP
            elif action == "night":
                if child_manager.start_app(app_registry[APP_ID_NIGHT]):
                    current_screen = RUNNING_APP
        elif current_screen == SETTINGS_MENU:
            if action == ROOT_MENU_2:
                session_root_page = ROOT_MENU_2
                current_screen = ROOT_MENU_2
            elif action == "network":
                current_screen = NETWORK_STATUS
            elif action == "pi_stats":
                current_screen = PI_STATS_STATUS
            elif action == "logs":
                current_screen = LOGS_STATUS
        elif current_screen == SHUTDOWN_CONFIRM:
            if action == "confirm":
                child_manager.shutdown()
                if framebuffer is not None:
                    write_framebuffer_image(framebuffer, Image.new("RGB", (args.width, args.height), BG))
                return run_shutdown(args.shutdown_command)
            current_screen = ROOT_MENU_2
            session_root_page = ROOT_MENU_2
        elif current_screen == THEMES_MENU:
            if action == ROOT_MENU_2:
                current_screen = ROOT_MENU_2
                session_root_page = ROOT_MENU_2
            elif action in THEME_PICKER_COLUMNS:
                active_theme_id = action
                theme_state_store.write_theme_id(active_theme_id)
                shell_images = build_shell_images(theme_catalog[active_theme_id], args.width, args.height)
                current_screen = THEMES_MENU
        elif current_screen == PIN_KEYPAD:
            if action in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0"}:
                entered_pin += action
            elif action == "cancel":
                entered_pin = ""
                current_screen = session_root_page
            elif action == "ok":
                result, consecutive_pin_failures = evaluate_pin_entry(entered_pin, args.pin, consecutive_pin_failures)
                entered_pin = ""
                if result == "success":
                    pending_pin_shutdown = False
                    current_screen = ACCESS_GRANTED
                elif result == "retry":
                    pending_pin_shutdown = False
                    current_screen = ACCESS_DENIED
                else:
                    pending_pin_shutdown = True
                    current_screen = ACCESS_DENIED
        else:
            current_screen = session_root_page
    child_manager.shutdown()
    return 1 if STOP_REQUESTED else 0


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
    night_app = app_registry[APP_ID_NIGHT]
    theme_catalog = load_theme_catalog(Path(args.theme_root))
    theme_state_store = ThemeStateStore(args.theme_state_path)
    active_theme_id = validate_theme_selection(load_theme_selection(theme_state_store, theme_catalog, args.default_theme), theme_catalog)
    theme_state_store.write_theme_id(active_theme_id)

    if args.dump_contracts:
        print(json.dumps(build_contract_snapshot(app_registry, night_app, str(mode_store.path), args, theme_catalog, active_theme_id), indent=2), flush=True)
        return 0

    if args.probe_touch:
        return run_touch_probe(args.width)

    shell_images = build_shell_images(theme_catalog[active_theme_id], args.width, args.height)
    save_preview(shell_images.screens[ROOT_MENU_1], args.output_selector)

    framebuffer = None
    if not args.no_framebuffer:
        if not Path(args.fbdev).exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        framebuffer = FramebufferWriter(args.fbdev, args.width, args.height)
        framebuffer.open()

    touch_reader = TouchReader(args.width, args.height)
    try:
        if not args.skip_gif:
            playback_gif(framebuffer, Path(args.gif), args.width, args.height, args.gif_speed, args.output_gif_first, args.output_gif_last)
        if args.no_framebuffer:
            print("Skipping touch loop because --no-framebuffer was set.", flush=True)
            return 0
        return run_main_screen_shell(args, framebuffer, touch_reader, mode_store, app_registry, theme_catalog, theme_state_store, shell_images, active_theme_id)
    finally:
        touch_reader.close()
        if framebuffer is not None:
            framebuffer.close()


if __name__ == "__main__":
    raise SystemExit(main())
