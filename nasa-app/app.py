#!/usr/bin/env python3
"""Standalone NASA/ISS framebuffer app for zero2dash."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
import json
import mmap
import os
from pathlib import Path
import re
import select
import shutil
import signal
import struct
import sys
import time
from typing import Any
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from display_layout import LAYOUT_HALF, centred_text_y, ellipsize_text, fit_font, truncate_pair

import touch_calibration


APP_NAME = "NASA ISS"
ASSETS_DIR = SCRIPT_DIR / "assets"
FONTS_DIR = SCRIPT_DIR / "fonts"
COUNTRY_MAP_PATH = SCRIPT_DIR / "country_codes.json"
LOCATION_CACHE_PATH = SCRIPT_DIR / "location_cache.json"
CREW_CACHE_PATH = SCRIPT_DIR / "crew_cache.json"
LEGACY_ERROR_ASSET_PATH = ASSETS_DIR / "nasa_error.png"
MAP_TEMPLATE_PATH = ASSETS_DIR / "map.png"
MAP_STALE_TEMPLATE_PATH = ASSETS_DIR / "map-error.png"
DETAILS_TEMPLATE_PATH = ASSETS_DIR / "iss-background.png"
CREW_TEMPLATE_PATH = ASSETS_DIR / "people-background.png"
CREW_STALE_TEMPLATE_PATH = ASSETS_DIR / "people-error.png"
ERROR_TEMPLATE_PATH = ASSETS_DIR / "error-background.png"

FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
CANVAS_WIDTH = 320
CANVAS_HEIGHT = 240
LEFT_STRIP_WIDTH = 32
PAGE_CYCLE_SECS = 10.0
LOCATION_REFRESH_SECS = 120.0
TOUCH_SETTLE_SECS = 0.20
TOUCH_DEBOUNCE_SECS = 0.20
HOLD_TO_EXIT_SECS = 2.0
HTTP_TIMEOUT_SECS = 3.0
LIVE_FETCH_RETRIES = 1
TEXT_RGB = (245, 245, 245)
MUTED_RGB = (163, 176, 194)
WARNING_RGB = (255, 198, 64)
ACCENT_RGB = (255, 208, 64)
BACKGROUND_RGB = (8, 16, 28)
RESAMPLING_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
WTIA_SAT_URL = "https://api.wheretheiss.at/v1/satellites/25544"
WTIA_COORDS_URL = "https://api.wheretheiss.at/v1/coordinates/{lat:.6f},{lon:.6f}"
WTIA_POSITIONS_URL = "https://api.wheretheiss.at/v1/satellites/25544/positions"
OPEN_NOTIFY_ISS_URL = "http://api.open-notify.org/iss-now.json"
CORQUAID_CREW_URL = "https://corquaid.github.io/international-space-station-APIs/JSON/people-in-space.json"
OPEN_NOTIFY_CREW_URL = "http://api.open-notify.org/astros.json"
USER_AGENT = 'zero2dash-nasa/1.0'
DETAILS_TITLE_FONT_NAME = 'Stay On The Ground Distressed.ttf'

_STOP_REQUESTED = False

EV_KEY = 0x01
EV_ABS = 0x03
ABS_X = 0x00
ABS_Y = 0x01
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39
BTN_TOUCH = 0x14A
INPUT_EVENT_STRUCT = struct.Struct("llHHI")


# NASA operator layout controls.
# Edit `*_X` / `*_Y` to move content, `*_WIDTH` / `*_HEIGHT` to resize the
# usable area, `*_FONT_SIZE` to change text size, and `*_FONT_NAME` to swap
# the font file used from `nasa-app/fonts/` without touching the render logic.
# `map-guide.png` defines a full-width band with 40px top/bottom margins.
MAP_OVERLAY_X = 0
MAP_OVERLAY_Y = 40
MAP_OVERLAY_WIDTH = 320
MAP_OVERLAY_HEIGHT = 160

# `text-box.png` defines a 260x180 box at x=30, y=30 for details/crew text.
# Edit these bounds if the guide image changes.
DETAILS_CONTENT_X = 30
DETAILS_CONTENT_Y = 30
DETAILS_CONTENT_WIDTH = 260
DETAILS_ROW_HEIGHT = 28
DETAILS_LABEL_GAP = 8
DETAILS_VALUE_WIDTH = 156
DETAILS_LABEL_FONT_NAME = DETAILS_TITLE_FONT_NAME
DETAILS_LABEL_FONT_SIZE = 11
DETAILS_VALUE_FONT_NAME = "NotoSans-Regular.ttf"
DETAILS_VALUE_FONT_SIZE = 11
DETAILS_BODY_FONT_NAME = "NotoSans-Regular.ttf"
DETAILS_BODY_FONT_SIZE = 9
DETAILS_REASON_X = 30
DETAILS_REASON_Y = 170
DETAILS_REASON_WIDTH = 260
DETAILS_REASON_LINE_HEIGHT = 12
DETAILS_REASON_MAX_LINES = 2

# Crew page text block and page badge.
CREW_NAME_FONT_NAME = DETAILS_TITLE_FONT_NAME
CREW_NAME_FONT_SIZE = 16
CREW_DETAIL_FONT_NAME = "NotoSans-Regular.ttf"
CREW_DETAIL_FONT_SIZE = 11
CREW_CONTENT_X = 30
CREW_CONTENT_WIDTH = 260
CREW_PAGE_BADGE_X = 228
CREW_PAGE_BADGE_Y = 34
CREW_PAGE_BADGE_WIDTH = 58
CREW_PAGE_BADGE_HEIGHT = 18
# Edit these centre points to move each visible crew row vertically.
CREW_SLOT_NAME_CENTRES = (47, 108, 169)
CREW_SLOT_DETAIL_1_CENTRES = (67, 128, 189)
CREW_SLOT_DETAIL_2_CENTRES = (84, 145, 206)

@dataclass(frozen=True)
class OrbitPoint:
    timestamp: int
    latitude: float
    longitude: float


@dataclass(frozen=True)
class LocationSnapshot:
    source: str
    fetched_at: int
    position_timestamp: int
    latitude: float
    longitude: float
    altitude_km: float | None
    velocity_kmh: float | None
    country_code: str
    country_name: str
    location_label: str
    visibility: str
    trail: list[OrbitPoint]
    details_timestamp: int


@dataclass(frozen=True)
class CrewMember:
    name: str
    role: str
    spacecraft: str
    agency: str
    launched: int | None
    days_in_space_prior: int | None
    days_in_space_current: int | None
    secondary: str


@dataclass(frozen=True)
class CrewSnapshot:
    source: str
    fetched_at: int
    crew: list[CrewMember]
    expedition: str
    expedition_reason: str


@dataclass(frozen=True)
class PageState:
    image: Image.Image
    kind: str
    stale: bool


def request_stop(_signum: int, _frame: object) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the standalone NASA/ISS app.")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
    parser.add_argument("--location-cache", default=str(LOCATION_CACHE_PATH), help=f"Location/details cache path (default: {LOCATION_CACHE_PATH})")
    parser.add_argument("--crew-cache", default=str(CREW_CACHE_PATH), help=f"Crew cache path (default: {CREW_CACHE_PATH})")
    parser.add_argument("--output", help="Optional output PNG path for local verification.")
    parser.add_argument("--page", choices=("map", "details", "crew", "error"), help="Render a single page and exit.")
    parser.add_argument("--offline", action="store_true", help="Skip live API calls and use cache/error paths only.")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer writes for safe verification.")
    parser.add_argument("--self-test", action="store_true", help="Run inline smoke tests and exit.")
    return parser.parse_args()


def ensure_directories() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FONTS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_local_fonts() -> None:
    targets = {
        "NotoSans-Regular.ttf": [
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/NotoSans-Regular.ttf",
            "C:/Windows/Fonts/DejaVuSans.ttf",
            "C:/Windows/Fonts/LiberationSans-Regular.ttf",
        ],
        "NotoSans-Bold.ttf": [
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/NotoSans-Bold.ttf",
            "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/LiberationSans-Bold.ttf",
        ],
    }
    for filename, candidates in targets.items():
        target = FONTS_DIR / filename
        if target.exists():
            continue
        for candidate in candidates:
            source = Path(candidate)
            if source.exists():
                try:
                    shutil.copy2(source, target)
                    break
                except Exception:
                    continue


@lru_cache(maxsize=64)
def load_font(size: int, *, bold: bool = False, name: str | None = None):
    ensure_directories()
    ensure_local_fonts()
    candidates: list[Path] = []
    if name:
        candidates.append(FONTS_DIR / name)
    candidates.extend(
        [
            FONTS_DIR / ("NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"),
            FONTS_DIR / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
            FONTS_DIR / ("LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except Exception:
                continue
    return ImageFont.load_default()

def _continent(points: list[tuple[int, int]], width: int, height: int) -> list[tuple[int, int]]:
    return [(int(width * x / 320), int(height * y / 240)) for x, y in points]


def generate_world_map(path: Path, width: int = CANVAS_WIDTH, height: int = CANVAS_HEIGHT) -> None:
    image = Image.new("RGB", (width, height), (13, 33, 52))
    draw = ImageDraw.Draw(image)
    for x in range(0, width, max(1, width // 12)):
        draw.line((x, 0, x, height), fill=(20, 52, 76))
    for y in range(0, height, max(1, height // 6)):
        draw.line((0, y, width, y), fill=(20, 52, 76))
    land_rgb = (78, 116, 72)
    outlines = [
        [(20, 52), (62, 36), (88, 42), (103, 66), (80, 88), (70, 110), (51, 118), (30, 95)],
        [(86, 118), (106, 136), (116, 172), (96, 208), (77, 196), (69, 158)],
        [(158, 42), (196, 36), (244, 48), (278, 62), (298, 88), (286, 112), (244, 104), (208, 106), (188, 96), (174, 78)],
        [(170, 96), (188, 110), (198, 152), (182, 196), (158, 188), (146, 154), (156, 118)],
        [(266, 148), (292, 162), (304, 190), (284, 206), (254, 192), (248, 164)],
        [(92, 24), (106, 13), (122, 20), (118, 42), (100, 46)],
        [(116, 205), (210, 202), (274, 212), (305, 224), (296, 235), (104, 232)],
    ]
    for polygon in outlines:
        draw.polygon(_continent(polygon, width, height), fill=land_rgb, outline=(117, 158, 110))
    title_font = load_font(15, bold=True)
    draw.rounded_rectangle((10, 8, width - 10, 30), radius=10, fill=(6, 18, 32))
    draw.text((16, centred_text_y(title_font, "World Map", 19)), "World Map", font=title_font, fill=(230, 240, 248))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def generate_error_image(path: Path, width: int = CANVAS_WIDTH, height: int = CANVAS_HEIGHT) -> None:
    image = Image.new("RGB", (width, height), (19, 8, 14))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, width - 18, height - 18), radius=18, fill=(38, 14, 24), outline=(120, 42, 56), width=3)
    title_font = load_font(20, bold=True)
    body_font = load_font(14, bold=False)
    draw.text((54, 54), "!", font=load_font(58, bold=True), fill=(255, 186, 72))
    draw.text((102, 66), "NASA data unavailable", font=title_font, fill=(245, 230, 230))
    draw.text((54, 122), "Startup failed and no", font=body_font, fill=(224, 210, 214))
    draw.text((54, 144), "usable cache was found.", font=body_font, fill=(224, 210, 214))
    draw.text((54, 178), "Retry later.", font=body_font, fill=(255, 186, 72))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def ensure_assets() -> None:
    if not LEGACY_ERROR_ASSET_PATH.exists() and not ERROR_TEMPLATE_PATH.exists():
        generate_error_image(LEGACY_ERROR_ASSET_PATH)



def load_country_map() -> dict[str, str]:
    if not COUNTRY_MAP_PATH.exists():
        return {}
    try:
        payload = json.loads(COUNTRY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key).upper(): str(value) for key, value in payload.items()}


def save_preview(image: Image.Image, output_path: str | None) -> None:
    if not output_path:
        return
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    print(f"Saved preview image to {target}", flush=True)


def rgb888_to_rgb565(image: Image.Image) -> bytes:
    rgb = image.convert("RGB").tobytes()
    payload = bytearray((len(rgb) // 3) * 2)
    out_idx = 0
    for idx in range(0, len(rgb), 3):
        value = ((rgb[idx] & 0xF8) << 8) | ((rgb[idx + 1] & 0xFC) << 3) | (rgb[idx + 2] >> 3)
        payload[out_idx] = value & 0xFF
        payload[out_idx + 1] = (value >> 8) & 0xFF
        out_idx += 2
    return bytes(payload)


class FramebufferWriter:
    def __init__(self, fbdev: str, width: int, height: int) -> None:
        self.fbdev = fbdev
        self.width = width
        self.height = height
        self.expected = width * height * 2
        self._handle: Any | None = None
        self._mapping: mmap.mmap | None = None

    def open(self) -> None:
        handle = open(self.fbdev, "r+b", buffering=0)
        self._handle = handle
        self._mapping = mmap.mmap(handle.fileno(), self.expected, mmap.MAP_SHARED, mmap.PROT_WRITE)

    def write_frame(self, image: Image.Image) -> None:
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
    match = re.search(r"event(\d+)$", event_path)
    index = int(match.group(1)) if match else 999
    score = (7 if has_touch_abs else -7) + (5 if has_btn_touch else -1) + name_bonus
    reason = f"score={score}; name='{name or 'unknown'}'; touch_abs={'yes' if has_touch_abs else 'no'}; BTN_TOUCH={'yes' if has_btn_touch else 'no'}"
    return (score, int(has_touch_abs), int(has_btn_touch), -index), reason


def touch_probe() -> tuple[str | None, str]:
    forced = os.environ.get("TOUCH_DEVICE", "").strip() or os.environ.get("NASA_TOUCH_DEVICE", "").strip()
    if forced:
        resolved = f"/dev/input/{forced}" if forced.startswith("event") and forced[5:].isdigit() else forced
        if Path(resolved).exists():
            return resolved, f"forced by override {forced}"
        return None, f"configured override '{forced}' was not found"

    input_dir = Path("/dev/input")
    candidates = sorted(input_dir.glob("event*")) if input_dir.exists() else []
    if not candidates:
        return None, "no /dev/input/event* devices found"

    ranked: list[tuple[tuple[int, int, int, int], str, str]] = []
    for path in candidates:
        rank, reason = _touch_candidate_details(str(path))
        ranked.append((rank, str(path), reason))
    ranked.sort(reverse=True)
    best_rank, best_path, best_reason = ranked[0]
    if best_rank[0] <= 0:
        return None, best_reason
    return best_path, best_reason


def _candidate_absinfo_paths(device: str) -> list[Path]:
    device_path = Path(device)
    return [
        Path("/sys/class/input") / device_path.name / "device" / "absinfo",
        Path("/sys/class/input") / device_path.name / "device" / "device" / "absinfo",
    ]


def detect_touch_bounds(device: str, default_width: int, default_height: int) -> tuple[int, int, int, int]:
    x_width = default_width
    x_min = 0
    y_height = default_height
    y_min = 0
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
                        continue
                    parts = payload.strip().split()
                    if len(parts) < 3:
                        continue
                    try:
                        min_val = int(parts[1])
                        max_val = int(parts[2])
                    except ValueError:
                        continue
                    if max_val <= min_val:
                        continue
                    size = max_val - min_val + 1
                    if code in (ABS_X, ABS_MT_POSITION_X):
                        x_width = max(100, size)
                        x_min = min_val
                    elif code in (ABS_Y, ABS_MT_POSITION_Y):
                        y_height = max(100, size)
                        y_min = min_val
        except Exception:
            continue
    return x_width, x_min, y_height, y_min


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
        self.device, self.reason = touch_probe()
        self.handle = None
        self.touch_width = screen_width
        self.touch_min_x = 0
        self.touch_height = screen_height
        self.touch_min_y = 0
        self.last_x = 0
        self.last_y = 0
        self.touch_down = False
        self.touch_started_at = 0.0
        self.last_emit = 0.0
        if self.device:
            self.touch_width, self.touch_min_x, self.touch_height, self.touch_min_y = detect_touch_bounds(self.device, screen_width, screen_height)
            self.handle = open(self.device, "rb", buffering=0)

    def is_available(self) -> bool:
        return self.handle is not None and self.device is not None

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def read_action(self, timeout_secs: float) -> str | None:
        if self.handle is None or self.device is None:
            if timeout_secs > 0:
                time.sleep(timeout_secs)
            return None
        readable, _, _ = select.select([self.handle], [], [], timeout_secs)
        if not readable:
            return None
        raw = self.handle.read(INPUT_EVENT_STRUCT.size)
        if len(raw) != INPUT_EVENT_STRUCT.size:
            return None
        _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)
        if ev_type == EV_ABS and ev_code in (ABS_X, ABS_MT_POSITION_X):
            self.last_x = ev_value
        elif ev_type == EV_ABS and ev_code in (ABS_Y, ABS_MT_POSITION_Y):
            self.last_y = ev_value
        elif ev_type == EV_KEY and ev_code == BTN_TOUCH:
            if ev_value == 1:
                self.touch_down = True
                self.touch_started_at = time.monotonic()
            elif ev_value == 0 and self.touch_down:
                return self._release_action()
        elif ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
            if ev_value >= 0:
                self.touch_down = True
                self.touch_started_at = time.monotonic()
            elif ev_value == -1 and self.touch_down:
                return self._release_action()
        return None

    def _release_action(self) -> str | None:
        self.touch_down = False
        now = time.monotonic()
        duration = max(0.0, now - self.touch_started_at)
        if (now - self.last_emit) < TOUCH_DEBOUNCE_SECS:
            return None
        self.last_emit = now
        screen_x, _screen_y = _map_touch_to_screen(self.device, self.last_x, self.last_y, self.screen_width, self.screen_height, self.touch_width, self.touch_min_x, self.touch_height, self.touch_min_y)
        if duration >= HOLD_TO_EXIT_SECS:
            return "HOLD"
        if screen_x < LEFT_STRIP_WIDTH:
            return "EXIT"
        return None


def expand_path(value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (SCRIPT_DIR / candidate).resolve()


def fetch_json(url: str, *, timeout_secs: float = HTTP_TIMEOUT_SECS) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_secs) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("API response was not a JSON object")
    return payload


def retry_call(callable_obj, attempts: int = LIVE_FETCH_RETRIES):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return callable_obj()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.4 * (attempt + 1))
    if last_error is None:
        raise RuntimeError("retry_call failed without an error")
    raise last_error


def load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def clean_location_text(value: Any, *, uppercase: bool = False) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered in {"", "?", "??", "-", "--", "n/a", "na", "unknown", "tba", "none", "null"}:
        return ""
    return text.upper() if uppercase else text


def deserialize_location(payload: dict[str, Any]) -> LocationSnapshot | None:
    try:
        trail_payload = payload.get("trail", [])
        trail = [
            OrbitPoint(timestamp=int(point["timestamp"]), latitude=float(point["latitude"]), longitude=float(point["longitude"]))
            for point in trail_payload
            if isinstance(point, dict)
        ]
        country_code = clean_location_text(payload.get("country_code", ""), uppercase=True)
        country_name = clean_location_text(payload.get("country_name", ""))
        location_label = clean_location_text(payload.get("location_label", ""))
        return LocationSnapshot(
            source=str(payload["source"]),
            fetched_at=int(payload["fetched_at"]),
            position_timestamp=int(payload["position_timestamp"]),
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            altitude_km=float(payload["altitude_km"]) if payload.get("altitude_km") is not None else None,
            velocity_kmh=float(payload["velocity_kmh"]) if payload.get("velocity_kmh") is not None else None,
            country_code=country_code,
            country_name=country_name,
            location_label=location_label,
            visibility=str(payload.get("visibility", payload.get("flyover_status", "TBA"))).strip() or "TBA",
            trail=trail,
            details_timestamp=int(payload.get("details_timestamp", payload["position_timestamp"])),
        )
    except Exception:
        return None


def serialize_location(snapshot: LocationSnapshot) -> dict[str, Any]:
    payload = asdict(snapshot)
    payload["trail"] = [asdict(point) for point in snapshot.trail]
    return payload


def deserialize_crew(payload: dict[str, Any]) -> CrewSnapshot | None:
    try:
        crew_list = []
        for item in payload.get("crew", []):
            if not isinstance(item, dict):
                continue
            crew_list.append(
                CrewMember(
                    name=str(item.get("name", "")),
                    role=str(item.get("role", "")),
                    spacecraft=str(item.get("spacecraft", "")),
                    agency=str(item.get("agency", "")),
                    launched=int(item["launched"]) if item.get("launched") is not None else None,
                    days_in_space_prior=int(item["days_in_space_prior"]) if item.get("days_in_space_prior") is not None else None,
                    days_in_space_current=int(item["days_in_space_current"]) if item.get("days_in_space_current") is not None else None,
                    secondary=str(item.get("secondary", "")),
                )
            )
        return CrewSnapshot(
            source=str(payload["source"]),
            fetched_at=int(payload["fetched_at"]),
            crew=crew_list,
            expedition=str(payload.get("expedition", "")),
            expedition_reason=str(payload.get("expedition_reason", "")),
        )
    except Exception:
        return None


def serialize_crew(snapshot: CrewSnapshot) -> dict[str, Any]:
    return {
        "source": snapshot.source,
        "fetched_at": snapshot.fetched_at,
        "crew": [asdict(item) for item in snapshot.crew],
        "expedition": snapshot.expedition,
        "expedition_reason": snapshot.expedition_reason,
    }

def current_unix_time() -> int:
    return int(time.time())


def safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def iso_country_name(country_code: str, country_map: dict[str, str]) -> str:
    if not country_code:
        return ""
    return country_map.get(country_code.upper(), "")


def compute_trail_timestamps(timestamp_value: int) -> list[int]:
    offsets = (-600, -450, -300, -150, 0, 150, 300, 450, 600)
    return [timestamp_value + offset for offset in offsets]


def fetch_trail(timestamp_value: int) -> list[OrbitPoint]:
    query = urllib.parse.urlencode({"timestamps": ",".join(str(item) for item in compute_trail_timestamps(timestamp_value))})
    payload = fetch_json(f"{WTIA_POSITIONS_URL}?{query}")
    points_raw = payload.get("positions", payload.get("data", payload))
    trail: list[OrbitPoint] = []
    if isinstance(points_raw, list):
        for item in points_raw:
            if not isinstance(item, dict):
                continue
            lat = safe_float(item.get("latitude"))
            lon = safe_float(item.get("longitude"))
            ts = safe_int(item.get("timestamp"))
            if lat is None or lon is None or ts is None:
                continue
            trail.append(OrbitPoint(timestamp=ts, latitude=lat, longitude=lon))
    return trail


def build_live_location(country_map: dict[str, str], cached: LocationSnapshot | None) -> tuple[LocationSnapshot, bool, bool]:
    now_ts = current_unix_time()
    sat_payload = retry_call(lambda: fetch_json(WTIA_SAT_URL))
    latitude = safe_float(sat_payload.get("latitude"))
    longitude = safe_float(sat_payload.get("longitude"))
    timestamp_value = safe_int(sat_payload.get("timestamp")) or now_ts
    altitude_km = safe_float(sat_payload.get("altitude"))
    velocity_kmh = safe_float(sat_payload.get("velocity"))
    visibility = str(sat_payload.get("visibility", "")).strip().title()
    if latitude is None or longitude is None:
        raise ValueError("live location payload is missing latitude/longitude")

    country_code = ""
    country_name = ""
    details_timestamp = timestamp_value
    map_stale = False
    details_stale = False
    if altitude_km is None and cached is not None and cached.altitude_km is not None:
        altitude_km = cached.altitude_km
        details_stale = True
    if velocity_kmh is None and cached is not None and cached.velocity_kmh is not None:
        velocity_kmh = cached.velocity_kmh
        details_stale = True
    if not visibility and cached is not None and cached.visibility:
        visibility = cached.visibility
        details_stale = True
    if not visibility:
        visibility = "TBA"

    try:
        geocode = fetch_json(WTIA_COORDS_URL.format(lat=latitude, lon=longitude))
        country_code = clean_location_text(geocode.get("country_code", ""), uppercase=True)
        country_name = iso_country_name(country_code, country_map)
    except Exception:
        if cached is not None:
            country_code = clean_location_text(cached.country_code, uppercase=True)
            country_name = clean_location_text(cached.country_name)
            details_stale = True
            details_timestamp = cached.details_timestamp

    try:
        trail = fetch_trail(timestamp_value)
    except Exception:
        trail = cached.trail if cached is not None else []
        if trail:
            map_stale = True

    location_label = country_name or country_code or "International Waters"
    if not country_name and not country_code:
        location_label = "International Waters"

    snapshot = LocationSnapshot(
        source="wheretheiss",
        fetched_at=now_ts,
        position_timestamp=timestamp_value,
        latitude=latitude,
        longitude=longitude,
        altitude_km=altitude_km,
        velocity_kmh=velocity_kmh,
        country_code=country_code,
        country_name=country_name,
        location_label=location_label,
        visibility=visibility,
        trail=trail,
        details_timestamp=details_timestamp,
    )
    return snapshot, map_stale, details_stale


def build_fallback_location(cached: LocationSnapshot | None) -> tuple[LocationSnapshot, bool, bool]:
    payload = retry_call(lambda: fetch_json(OPEN_NOTIFY_ISS_URL))
    position = payload.get("iss_position", {})
    latitude = safe_float(position.get("latitude"))
    longitude = safe_float(position.get("longitude"))
    timestamp_value = safe_int(payload.get("timestamp")) or current_unix_time()
    if latitude is None or longitude is None:
        raise ValueError("fallback location payload is missing latitude/longitude")
    snapshot = LocationSnapshot(
        source="open-notify",
        fetched_at=current_unix_time(),
        position_timestamp=timestamp_value,
        latitude=latitude,
        longitude=longitude,
        altitude_km=cached.altitude_km if cached is not None else None,
        velocity_kmh=cached.velocity_kmh if cached is not None else None,
        country_code=cached.country_code if cached is not None else "",
        country_name=cached.country_name if cached is not None else "",
        location_label=cached.location_label if cached is not None else "International Waters",
        visibility=cached.visibility if cached is not None and cached.visibility else "TBA",
        trail=cached.trail if cached is not None else [],
        details_timestamp=cached.details_timestamp if cached is not None else timestamp_value,
    )
    return snapshot, bool(cached is not None and cached.trail), True


def resolve_location(country_map: dict[str, str], cache_path: Path, offline: bool) -> tuple[LocationSnapshot | None, bool, bool, bool]:
    cached = deserialize_location(load_json_file(cache_path) or {})
    if offline:
        return cached, cached is not None, True, True
    try:
        live, map_stale, details_stale = build_live_location(country_map, cached)
        write_json_file(cache_path, serialize_location(live))
        return live, True, map_stale, details_stale
    except Exception:
        pass
    try:
        fallback, map_stale, details_stale = build_fallback_location(cached)
        write_json_file(cache_path, serialize_location(fallback))
        return fallback, True, map_stale, details_stale
    except Exception:
        pass
    if cached is not None:
        return cached, True, True, True
    return None, False, True, True

def _parse_launch_epoch(value: Any) -> int | None:
    epoch = safe_int(value)
    if epoch is not None:
        return epoch
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            if cleaned.endswith("Z"):
                cleaned = cleaned[:-1] + "+00:00"
            return int(datetime.fromisoformat(cleaned).timestamp())
        except ValueError:
            return None
    return None


def build_secondary(role: str, spacecraft: str, agency: str, days_current: int | None) -> str:
    if days_current is not None:
        return f"{role or 'Crew'} | {days_current}d in space"
    if role and spacecraft:
        return f"{role} | {spacecraft}"
    if spacecraft:
        return spacecraft
    if agency:
        return agency
    return role or "ISS crew"


def compact_text(value: Any, limit: int = 56) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    text = re.split(r"(?<=[.!?])\s+", text)[0]
    return text if len(text) <= limit else f"{text[: limit - 3].rstrip()}..."


def normalise_expedition(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("expedition"):
        return raw
    digits = "".join(ch for ch in raw if ch.isdigit())
    return f"Expedition {digits}" if digits else raw


def mission_text_from_payload(payload: dict[str, Any], entries: list[dict[str, Any]]) -> str:
    for key in ("expedition_reason", "mission", "summary", "description", "title"):
        value = compact_text(payload.get(key))
        if value:
            return value
    for item in entries:
        for key in ("mission", "summary", "description", "short_bio", "bio", "title"):
            value = compact_text(item.get(key))
            if value:
                return value
    return ""


def build_expedition_reason(expedition: str, mission_text: str, crew: list[CrewMember]) -> str:
    if mission_text:
        return mission_text
    if expedition and crew:
        return compact_text(f"{expedition} | {crew[0].role or crew[0].spacecraft or 'ISS crew'}")
    if expedition:
        return expedition
    if crew:
        lead = crew[0]
        return compact_text(lead.role or lead.secondary or lead.spacecraft or "ISS crew")
    return "TBA"


def parse_corquaid_crew(payload: dict[str, Any]) -> tuple[list[CrewMember], str, str]:
    entries = payload.get("people", payload.get("crew", payload.get("data", [])))
    if not isinstance(entries, list):
        raise ValueError("crew payload is missing list data")
    now_ts = current_unix_time()
    crew: list[CrewMember] = []
    iss_entries: list[dict[str, Any]] = []
    expedition = normalise_expedition(payload.get("iss_expedition") or payload.get("expedition") or payload.get("expedition_number"))
    for item in entries:
        if not isinstance(item, dict):
            continue
        craft_name = str(item.get("craft", item.get("spacecraft", ""))).strip().upper()
        if not bool(item.get("iss")) and craft_name != "ISS":
            continue
        iss_entries.append(item)
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        role = str(item.get("position", "") or item.get("role", "")).strip()
        spacecraft = str(item.get("spacecraft", "")).strip() or "ISS"
        agency = str(item.get("agency", "")).strip()
        launched = _parse_launch_epoch(item.get("launched"))
        days_prior = safe_int(item.get("days_in_space"))
        days_current = days_prior
        if launched is not None and days_prior is not None:
            days_current = days_prior + max(0, (now_ts - launched) // 86400)
        item_expedition = normalise_expedition(item.get("expedition") or item.get("expedition_number"))
        if not expedition and item_expedition:
            expedition = item_expedition
        crew.append(CrewMember(name=name, role=role or "Crew", spacecraft=spacecraft, agency=agency, launched=launched, days_in_space_prior=days_prior, days_in_space_current=days_current, secondary=build_secondary(role, spacecraft, agency, days_current)))
    if not crew:
        raise ValueError("crew payload did not include ISS members")
    mission_text = mission_text_from_payload(payload, iss_entries)
    return crew, expedition, build_expedition_reason(expedition, mission_text, crew)


def parse_open_notify_crew(payload: dict[str, Any]) -> tuple[list[CrewMember], str, str]:
    entries = payload.get("people", [])
    if not isinstance(entries, list):
        raise ValueError("open-notify crew payload is missing list data")
    crew: list[CrewMember] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        if str(item.get("craft", "")).strip().upper() != "ISS":
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        crew.append(CrewMember(name=name, role="Astronaut", spacecraft="ISS", agency="", launched=None, days_in_space_prior=None, days_in_space_current=None, secondary="Astronaut | ISS"))
    if not crew:
        raise ValueError("open-notify did not include ISS crew")
    return crew, "", build_expedition_reason("", "", crew)


def resolve_crew(cache_path: Path, offline: bool) -> tuple[CrewSnapshot | None, bool]:
    cached = deserialize_crew(load_json_file(cache_path) or {})
    if offline:
        return cached, cached is not None
    try:
        crew, expedition, expedition_reason = retry_call(lambda: parse_corquaid_crew(fetch_json(CORQUAID_CREW_URL)))
        live = CrewSnapshot(source="corquaid", fetched_at=current_unix_time(), crew=crew, expedition=expedition, expedition_reason=expedition_reason)
        write_json_file(cache_path, serialize_crew(live))
        return live, False
    except Exception:
        pass
    try:
        crew, expedition, expedition_reason = retry_call(lambda: parse_open_notify_crew(fetch_json(OPEN_NOTIFY_CREW_URL)))
        fallback = CrewSnapshot(source="open-notify", fetched_at=current_unix_time(), crew=crew, expedition=expedition, expedition_reason=expedition_reason)
        write_json_file(cache_path, serialize_crew(fallback))
        return fallback, False
    except Exception:
        pass
    return cached, cached is not None

def format_timestamp(timestamp_value: int | None) -> str:
    if timestamp_value is None:
        return "Unknown"
    return datetime.fromtimestamp(timestamp_value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def paginate_crew(crew: list[CrewMember], page_size: int = 3) -> list[list[CrewMember]]:
    if not crew:
        return [[]]
    return [crew[index : index + page_size] for index in range(0, len(crew), page_size)]

def _load_asset_cached(path: Path) -> Image.Image:
    if path.exists():
        with Image.open(path) as image:
            return image.convert("RGB").resize((CANVAS_WIDTH, CANVAS_HEIGHT), RESAMPLING_LANCZOS)
    return Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BACKGROUND_RGB)


@lru_cache(maxsize=32)
def load_asset(path: Path) -> Image.Image:
    return _load_asset_cached(path)


@lru_cache(maxsize=16)
def load_asset_candidates(*paths: Path) -> Image.Image:
    for path in paths:
        if path.exists():
            return load_asset(path).copy()
    return Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BACKGROUND_RGB)

def rounded_panel_mask(width: int, height: int, radius: int) -> Image.Image:
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    return mask


def paste_rounded_panel(base: Image.Image, panel: Image.Image, box: tuple[int, int, int, int], *, radius: int) -> None:
    width = max(1, box[2] - box[0])
    height = max(1, box[3] - box[1])
    panel_image = panel.resize((width, height), RESAMPLING_LANCZOS)
    base.paste(panel_image, box[:2], rounded_panel_mask(width, height, radius))

def overlay_bounds(x: int, y: int, width: int, height: int) -> tuple[int, int, int, int]:
    return (x, y, x + width, y + height)


def clamp_point(x: int, y: int, box: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = box
    return (max(left, min(right, x)), max(top, min(bottom, y)))


def map_point(latitude: float, longitude: float, box: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = box
    width = max(1, right - left)
    height = max(1, bottom - top)
    x = left + int(((longitude + 180.0) / 360.0) * width)
    y = top + int(((90.0 - latitude) / 180.0) * height)
    return clamp_point(x, y, box)


def wrap_text_lines(draw: ImageDraw.ImageDraw, text: str, font, width_limit: int, max_lines: int) -> list[str]:
    words = (text.strip() or "TBA").split()
    if not words:
        return ["TBA"]
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textbbox((0, 0), trial, font=font)[2] <= width_limit or not current:
            current = trial
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if not lines:
        lines = ["TBA"]
    lines = lines[:max_lines]
    lines[-1] = ellipsize_text(lines[-1], font, width_limit)
    return lines


def location_display_name(location: LocationSnapshot) -> str:
    country_name = clean_location_text(location.country_name)
    location_label = clean_location_text(location.location_label)
    country_code = clean_location_text(location.country_code, uppercase=True)
    if country_name:
        return country_name
    if location_label:
        return location_label
    if country_code:
        return country_code
    return "International Waters"


def draw_badge(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, *, fill: tuple[int, int, int], text_fill: tuple[int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=8, fill=fill)
    font = load_font(12, bold=True)
    draw.text((box[0] + 8, centred_text_y(font, label, (box[1] + box[3]) // 2)), label, font=font, fill=text_fill)


def render_map_page(location: LocationSnapshot, *, stale: bool) -> Image.Image:
    image = load_asset_candidates(MAP_STALE_TEMPLATE_PATH if stale else MAP_TEMPLATE_PATH, MAP_TEMPLATE_PATH, ERROR_TEMPLATE_PATH)
    draw = ImageDraw.Draw(image)
    map_box = overlay_bounds(MAP_OVERLAY_X, MAP_OVERLAY_Y, MAP_OVERLAY_WIDTH, MAP_OVERLAY_HEIGHT)
    if location.trail:
        previous = None
        for point in location.trail:
            current = map_point(point.latitude, point.longitude, map_box)
            if previous is not None and abs(current[0] - previous[0]) < (map_box[2] - map_box[0]) // 2:
                draw.line((previous[0], previous[1], current[0], current[1]), fill=(255, 208, 64), width=3)
            previous = current
    marker_x, marker_y = map_point(location.latitude, location.longitude, map_box)
    draw.ellipse((marker_x - 5, marker_y - 5, marker_x + 5, marker_y + 5), fill=(255, 70, 70), outline=(255, 245, 245), width=2)
    return image


def render_details_page(location: LocationSnapshot, expedition_reason: str, *, stale: bool) -> Image.Image:
    image = load_asset_candidates(ERROR_TEMPLATE_PATH if stale else DETAILS_TEMPLATE_PATH, DETAILS_TEMPLATE_PATH)
    draw = ImageDraw.Draw(image)
    line_font = load_font(DETAILS_LABEL_FONT_SIZE, bold=True, name=DETAILS_LABEL_FONT_NAME)
    value_font = load_font(DETAILS_VALUE_FONT_SIZE, bold=False, name=DETAILS_VALUE_FONT_NAME)
    body_font = load_font(DETAILS_BODY_FONT_SIZE, bold=False, name=DETAILS_BODY_FONT_NAME)

    entries = [
        ("Lon/Lat:", f"{location.longitude:.5f}, {location.latitude:.5f}"),
        ("Currently over:", location_display_name(location)),
        ("Visibility:", location.visibility or "TBA"),
        ("Velocity(km/h):", f"{location.velocity_kmh:,.0f}km/h" if location.velocity_kmh is not None else "Unknown"),
        ("Altitude:", f"{location.altitude_km:.0f}km" if location.altitude_km is not None else "Unknown"),
    ]
    row_centres = tuple(DETAILS_CONTENT_Y + (DETAILS_ROW_HEIGHT // 2) + (DETAILS_ROW_HEIGHT * index) for index in range(len(entries)))

    for (label, value), centre_y in zip(entries, row_centres):
        label_text = label
        value_text = ellipsize_text(str(value), value_font, DETAILS_VALUE_WIDTH)
        label_width = draw.textbbox((0, 0), label_text, font=line_font)[2]
        value_width = draw.textbbox((0, 0), value_text, font=value_font)[2]
        total_width = label_width + DETAILS_LABEL_GAP + value_width
        centred_x = DETAILS_CONTENT_X + max(0, (DETAILS_CONTENT_WIDTH - total_width) // 2)
        start_x = max(DETAILS_CONTENT_X, centred_x)
        draw.text((start_x, centred_text_y(line_font, label_text, centre_y)), label_text, font=line_font, fill=TEXT_RGB)
        draw.text((start_x + label_width + DETAILS_LABEL_GAP, centred_text_y(value_font, value_text, centre_y)), value_text, font=value_font, fill=TEXT_RGB)

    reason_label = "Expedition Reason:"
    reason_label_width = draw.textbbox((0, 0), reason_label, font=line_font)[2]
    draw.text((DETAILS_REASON_X + max(0, (DETAILS_REASON_WIDTH - reason_label_width) // 2), centred_text_y(line_font, reason_label, DETAILS_REASON_Y + 8)), reason_label, font=line_font, fill=TEXT_RGB)

    wrapped = wrap_text_lines(draw, expedition_reason or "TBA", body_font, DETAILS_REASON_WIDTH, DETAILS_REASON_MAX_LINES)
    reason_y = DETAILS_REASON_Y + 20
    for line in wrapped:
        width = draw.textbbox((0, 0), line, font=body_font)[2]
        draw.text((DETAILS_REASON_X + max(0, (DETAILS_REASON_WIDTH - width) // 2), reason_y), line, font=body_font, fill=(225, 225, 230))
        reason_y += DETAILS_REASON_LINE_HEIGHT
    return image

def render_crew_page(crew_page: list[CrewMember], page_number: int, total_pages: int, *, stale: bool) -> Image.Image:
    image = load_asset_candidates(CREW_STALE_TEMPLATE_PATH if stale else CREW_TEMPLATE_PATH, CREW_TEMPLATE_PATH, ERROR_TEMPLATE_PATH)
    draw = ImageDraw.Draw(image)
    name_font = load_font(CREW_NAME_FONT_SIZE, bold=True, name=CREW_NAME_FONT_NAME)
    detail_font = load_font(CREW_DETAIL_FONT_SIZE, bold=False, name=CREW_DETAIL_FONT_NAME)
    page_label = f"{page_number}/{total_pages}"
    draw_badge(
        draw,
        overlay_bounds(CREW_PAGE_BADGE_X, CREW_PAGE_BADGE_Y, CREW_PAGE_BADGE_WIDTH, CREW_PAGE_BADGE_HEIGHT),
        page_label,
        fill=(19, 31, 55),
        text_fill=TEXT_RGB,
    )
    if not crew_page:
        empty_text = "Crew data unavailable"
        width = draw.textbbox((0, 0), empty_text, font=detail_font)[2]
        draw.text(((CANVAS_WIDTH - width) // 2, 108), empty_text, font=detail_font, fill=TEXT_RGB)
        return image
    slots = tuple(zip(CREW_SLOT_NAME_CENTRES, CREW_SLOT_DETAIL_1_CENTRES, CREW_SLOT_DETAIL_2_CENTRES))
    for item, (name_y, detail_y1, detail_y2) in zip(crew_page, slots):
        name_text = ellipsize_text(item.name, name_font, CREW_CONTENT_WIDTH)
        detail_lines = wrap_text_lines(draw, item.secondary or item.role or "ISS crew", detail_font, CREW_CONTENT_WIDTH, 2)
        name_x = CREW_CONTENT_X + max(0, (CREW_CONTENT_WIDTH - draw.textbbox((0, 0), name_text, font=name_font)[2]) // 2)
        draw.text((name_x, centred_text_y(name_font, name_text, name_y)), name_text, font=name_font, fill=TEXT_RGB)
        line_1 = detail_lines[0] if detail_lines else ""
        line_2 = detail_lines[1] if len(detail_lines) > 1 else ""
        if line_1:
            line_1_x = CREW_CONTENT_X + max(0, (CREW_CONTENT_WIDTH - draw.textbbox((0, 0), line_1, font=detail_font)[2]) // 2)
            draw.text((line_1_x, centred_text_y(detail_font, line_1, detail_y1)), line_1, font=detail_font, fill=(225, 225, 230))
        if line_2:
            line_2_x = CREW_CONTENT_X + max(0, (CREW_CONTENT_WIDTH - draw.textbbox((0, 0), line_2, font=detail_font)[2]) // 2)
            draw.text((line_2_x, centred_text_y(detail_font, line_2, detail_y2)), line_2, font=detail_font, fill=(225, 225, 230))
    return image


def render_error_page() -> Image.Image:
    image = load_asset_candidates(ERROR_TEMPLATE_PATH, LEGACY_ERROR_ASSET_PATH)
    draw = ImageDraw.Draw(image)
    title_font = load_font(16, bold=True)
    body_font = load_font(12, bold=False)
    draw.rounded_rectangle((34, 82, CANVAS_WIDTH - 34, 176), radius=16, fill=(14, 18, 38), outline=(237, 174, 82), width=2)
    draw.text((60, 98), "Startup failed", font=title_font, fill=(255, 222, 182))
    draw.text((49, 122), "No live ISS data and no usable", font=body_font, fill=TEXT_RGB)
    draw.text((64, 140), "cache was found.", font=body_font, fill=TEXT_RGB)
    draw.text((91, 159), "Retry later.", font=body_font, fill=(255, 198, 148))
    return image


def build_pages(location: LocationSnapshot | None, crew_snapshot: CrewSnapshot | None, *, map_stale: bool, details_stale: bool, crew_stale: bool) -> list[PageState]:
    if location is None:
        return [PageState(image=render_error_page(), kind="error", stale=False)]
    crew_pages = paginate_crew(crew_snapshot.crew if crew_snapshot is not None else [])
    total_crew_pages = max(1, len(crew_pages))
    pages = [
        PageState(image=render_map_page(location, stale=map_stale), kind="map", stale=map_stale),
        PageState(image=render_details_page(location, crew_snapshot.expedition_reason if crew_snapshot is not None else "TBA", stale=details_stale), kind="details", stale=details_stale),
    ]
    for index, crew_page in enumerate(crew_pages, start=1):
        pages.append(PageState(image=render_crew_page(crew_page, index, total_crew_pages, stale=crew_stale), kind="crew", stale=crew_stale))
    return pages


def render_single_page(page_name: str, pages: list[PageState]) -> Image.Image:
    if page_name == "error":
        return render_error_page()
    for page in pages:
        if page.kind == page_name:
            return page.image
    return pages[0].image

def validate_args(args: argparse.Namespace) -> int | None:
    if args.width <= 0 or args.height <= 0:
        print("Width and height must be positive integers.", file=sys.stderr)
        return 1
    return None

def run_self_test() -> int:
    ensure_directories()
    ensure_local_fonts()
    ensure_assets()
    sample_location = LocationSnapshot(
        source="self-test",
        fetched_at=1700000000,
        position_timestamp=1700000000,
        latitude=51.5,
        longitude=-0.12,
        altitude_km=408.4,
        velocity_kmh=27600.0,
        country_code="GB",
        country_name="United Kingdom",
        location_label="United Kingdom",
        visibility="Daylight",
        trail=[OrbitPoint(timestamp=1699999500, latitude=48.0, longitude=-22.0), OrbitPoint(timestamp=1700000000, latitude=51.5, longitude=-0.12), OrbitPoint(timestamp=1700000500, latitude=56.0, longitude=18.0)],
        details_timestamp=1700000000,
    )
    sample_crew = CrewSnapshot(
        source="self-test",
        fetched_at=1700000000,
        crew=[
            CrewMember("Alice Example", "Commander", "ISS", "NASA", 1690000000, 100, 112, "Commander | 112d in space"),
            CrewMember("Bora Example", "Flight Engineer", "ISS", "ESA", 1690500000, 60, 71, "Flight Engineer | 71d in space"),
            CrewMember("Chen Example", "Flight Engineer", "ISS", "JAXA", 1691000000, 40, 50, "Flight Engineer | 50d in space"),
            CrewMember("Dina Example", "Mission Specialist", "ISS", "CSA", None, None, None, "Mission Specialist | ISS"),
        ],
        expedition="Expedition 72",
        expedition_reason="Expedition 72 | Commander",
    )
    pages = build_pages(sample_location, sample_crew, map_stale=False, details_stale=True, crew_stale=False)
    if len(pages) != 4:
        print(f"[nasa] self-test failed: expected 4 pages, found {len(pages)}", file=sys.stderr)
        return 1
    if deserialize_location(serialize_location(sample_location)) is None or deserialize_crew(serialize_crew(sample_crew)) is None:
        print("[nasa] self-test failed: cache round-trip failed", file=sys.stderr)
        return 1
    if paginate_crew(sample_crew.crew, 3)[1][0].name != "Dina Example":
        print("[nasa] self-test failed: crew pagination mismatch", file=sys.stderr)
        return 1
    print("[nasa] self-test passed", flush=True)
    return 0

def run_preview(args: argparse.Namespace, country_map: dict[str, str]) -> int:

    location_path = expand_path(args.location_cache)
    crew_path = expand_path(args.crew_cache)
    location, _location_ok, map_stale, details_stale = resolve_location(country_map, location_path, args.offline)
    crew_snapshot, crew_stale = resolve_crew(crew_path, args.offline)
    pages = build_pages(location, crew_snapshot, map_stale=map_stale, details_stale=details_stale, crew_stale=crew_stale)
    image = render_single_page(args.page or "map", pages)
    save_preview(image, args.output)
    return 0


def run_live(args: argparse.Namespace, country_map: dict[str, str]) -> int:
    location_path = expand_path(args.location_cache)
    crew_path = expand_path(args.crew_cache)
    location, location_ok, map_stale, details_stale = resolve_location(country_map, location_path, args.offline)
    crew_snapshot, crew_stale = resolve_crew(crew_path, args.offline)
    if not location_ok or location is None:
        image = render_error_page()
        save_preview(image, args.output)
        if args.no_framebuffer:
            return 1
        if not Path(args.fbdev).exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        framebuffer = FramebufferWriter(args.fbdev, args.width, args.height)
        framebuffer.open()
        try:
            framebuffer.write_frame(image.resize((args.width, args.height), RESAMPLING_LANCZOS))
            while not _STOP_REQUESTED:
                time.sleep(0.25)
        finally:
            framebuffer.close()
        return 1

    pages = build_pages(location, crew_snapshot, map_stale=map_stale, details_stale=details_stale, crew_stale=crew_stale)
    if args.output and args.no_framebuffer:
        save_preview(pages[0].image, args.output)
        return 0

    framebuffer = None
    if not args.no_framebuffer:
        if not Path(args.fbdev).exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        framebuffer = FramebufferWriter(args.fbdev, args.width, args.height)
        framebuffer.open()

    touch_reader = TouchReader(args.width, args.height)
    page_index = 0
    last_rendered_index = -1
    ready_after = time.monotonic() + TOUCH_SETTLE_SECS
    next_refresh_at = time.monotonic() + LOCATION_REFRESH_SECS
    next_page_at = time.monotonic() + PAGE_CYCLE_SECS

    try:
        while not _STOP_REQUESTED:
            if page_index != last_rendered_index:
                image = pages[page_index].image.resize((args.width, args.height), RESAMPLING_LANCZOS)
                if framebuffer is not None:
                    framebuffer.write_frame(image)
                last_rendered_index = page_index

            now = time.monotonic()
            if now >= next_refresh_at:
                location, _location_ok, map_stale, details_stale = resolve_location(country_map, location_path, args.offline)
                pages = build_pages(location, crew_snapshot, map_stale=map_stale, details_stale=details_stale, crew_stale=crew_stale)
                page_index = min(page_index, len(pages) - 1)
                last_rendered_index = -1
                next_refresh_at = now + LOCATION_REFRESH_SECS

            if now >= next_page_at:
                page_index = (page_index + 1) % len(pages)
                next_page_at = now + PAGE_CYCLE_SECS

            wait_timeout = max(0.05, min(next_refresh_at - now, next_page_at - now, 0.25))
            if touch_reader.is_available() and now >= ready_after:
                action = touch_reader.read_action(wait_timeout)
                if action in {"EXIT", "HOLD"}:
                    return 0
            else:
                time.sleep(wait_timeout)
    finally:
        touch_reader.close()
        if framebuffer is not None:
            framebuffer.close()
    return 0


def main() -> int:
    args = parse_args()
    validation_error = validate_args(args)
    if validation_error is not None:
        return validation_error

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    ensure_directories()
    ensure_local_fonts()
    ensure_assets()

    if args.self_test:
        return run_self_test()

    country_map = load_country_map()
    if args.page:
        return run_preview(args, country_map)
    return run_live(args, country_map)


if __name__ == "__main__":
    raise SystemExit(main())


