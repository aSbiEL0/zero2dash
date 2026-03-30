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


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


load_env_file(REPO_ROOT / ".env")


APP_NAME = "NASA ISS"
ASSETS_DIR = SCRIPT_DIR / "assets"
FONTS_DIR = SCRIPT_DIR / "fonts"
COUNTRY_MAP_PATH = SCRIPT_DIR / "country_codes.json"
LOCATION_CACHE_PATH = SCRIPT_DIR / "location_cache.json"
CREW_CACHE_PATH = SCRIPT_DIR / "crew_cache.json"
MAP_TEMPLATE_PATH = ASSETS_DIR / "map.png"
MAP_STALE_TEMPLATE_PATH = ASSETS_DIR / "map-error.png"
DETAILS_TEMPLATE_PATH = ASSETS_DIR / "iss-background.png"
CREW_TEMPLATE_PATH = ASSETS_DIR / "people-background.png"
CREW_STALE_TEMPLATE_PATH = ASSETS_DIR / "people-error.png"
ERROR_TEMPLATE_PATH = ASSETS_DIR / "error-background.png"
LOADING_TEMPLATE_PATH = ASSETS_DIR / "loading.png"
DETAILS_GUIDE_PATH = ASSETS_DIR / "text-columns-guide.png"

FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
CANVAS_WIDTH = 320
CANVAS_HEIGHT = 240
LEFT_STRIP_WIDTH = 32
PAGE_CYCLE_SECS = 7.0                                       # notes: change `PAGE_CYCLE_SECS` to control how long each page stays on
# screen before the app advances to the next page.
LOCATION_REFRESH_SECS = 90.0
TOUCH_SETTLE_SECS = 0.20
TOUCH_DEBOUNCE_SECS = 0.20
HOLD_TO_EXIT_SECS = 2.0
HTTP_TIMEOUT_SECS = 3.0
LIVE_FETCH_RETRIES = 2
TEXT_RGB = (245, 245, 245)
MUTED_RGB = (163, 176, 194)
WARNING_RGB = (255, 198, 64)
ACCENT_RGB = (255, 208, 64)
BACKGROUND_RGB = (8, 16, 28)
RESAMPLING_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
WTIA_SAT_URL = "https://api.wheretheiss.at/v1/satellites/25544"
WTIA_POSITIONS_URL = "https://api.wheretheiss.at/v1/satellites/25544/positions"
OPEN_NOTIFY_ISS_URL = "http://api.open-notify.org/iss-now.json"
CORQUAID_CREW_URL = "https://corquaid.github.io/international-space-station-APIs/JSON/people-in-space.json"
OPEN_NOTIFY_CREW_URL = "http://api.open-notify.org/astros.json"
GEOAPIFY_REVERSE_URL = "https://api.geoapify.com/v1/geocode/reverse"
GEOAPIFY_API_KEY_ENV = "GEOAPIFY_API_KEY"
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
GEOAPIFY_AQUATIC_KEYWORDS = (
    "ocean",
    "sea",
    "bay",
    "gulf",
    "strait",
    "channel",
    "lake",
    "river",
    "sound",
    "bight",
    "passage",
    "waters",
)
LOADING_STAGE_MESSAGES: dict[str, tuple[str, str, str]] = {
    "position": ("Fetching ISS position", "Contacting the live tracker", "Waiting for current coordinates"),
    "location": ("Resolving current location", "Reverse geocoding the ISS point", "Matching coordinates to a country"),
    "crew": ("Loading crew data", "Fetching the latest expedition roster", "Preparing the crew rotation pages"),
    "render": ("Rendering pages", "Formatting map, details, and crew views", "Preparing the framebuffer output"),
}
# notes: change the strings above if you want different live loading-status
# messages. To move the loading text box itself, edit `render_loading_page()`.


# NASA operator layout controls.
# Edit `*_X` / `*_Y` to move content, `*_WIDTH` / `*_HEIGHT` to resize the
# usable area, `*_FONT_SIZE` to change text size, and `*_FONT_NAME` to swap
# the font file used from `nasa-app/fonts/` without touching the render logic.
# `map-guide.png` defines a full-width band with 40px top/bottom margins.
MAP_OVERLAY_X = 0
MAP_OVERLAY_Y = 40
MAP_OVERLAY_WIDTH = 320
MAP_OVERLAY_HEIGHT = 160

# `text-columns-guide.png` defines a 260x180 details area at x=30, y=30:
# left column 120px, gap 20px, right column 120px.
# notes: move both text columns together by changing `DETAILS_CONTENT_X` and
# `DETAILS_CONTENT_Y`. Move only the left labels with `DETAILS_LABEL_X`, only
# the right values with `DETAILS_VALUE_X`, and spread/tighten the rows with
# `DETAILS_ROW_HEIGHT`. If text clips, increase the matching `*_WIDTH` or
# reduce the matching font size.
DETAILS_CONTENT_X = 30
DETAILS_CONTENT_Y = 50
DETAILS_CONTENT_WIDTH = 260
DETAILS_CONTENT_HEIGHT = 180
DETAILS_ROW_HEIGHT = 30
DETAILS_LABEL_X = 30
DETAILS_LABEL_WIDTH = 120
DETAILS_VALUE_X = 170
DETAILS_VALUE_WIDTH = 120
DETAILS_LABEL_FONT_NAME = "Stencil.ttf"
DETAILS_LABEL_FONT_SIZE = 14
DETAILS_VALUE_FONT_NAME = "NotoSans-Regular.ttf"
DETAILS_VALUE_FONT_SIZE = 14
# notes: the stale badge is independent from the two columns. Move it with
# `DETAILS_STALE_BADGE_X` and `DETAILS_STALE_BADGE_Y`.
DETAILS_STALE_BADGE_X = 238
DETAILS_STALE_BADGE_Y = 28
DETAILS_STALE_BADGE_WIDTH = 58
DETAILS_STALE_BADGE_HEIGHT = 18

# Crew page text block and page badge.
CREW_NAME_FONT_NAME = "Stencil.ttf"
CREW_NAME_FONT_SIZE = 22
CREW_DETAIL_FONT_NAME = "NotoSans-Regular.ttf"
CREW_DETAIL_FONT_SIZE = 15
CREW_CONTENT_X = 30
CREW_CONTENT_WIDTH = 260
CREW_PAGE_BADGE_X = 228
CREW_PAGE_BADGE_Y = 28
CREW_PAGE_BADGE_WIDTH = 58
CREW_PAGE_BADGE_HEIGHT = 18
CREW_HEADER_FONT_NAME = DETAILS_TITLE_FONT_NAME
CREW_HEADER_FONT_SIZE = 17
CREW_HEADER_Y = 31
# Edit these centre points to move each visible crew row vertically.
CREW_SLOT_NAME_CENTRES = (58, 160)
CREW_SLOT_DETAIL_1_CENTRES = (88, 180)
CREW_SLOT_DETAIL_2_CENTRES = (110, 196)

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


@dataclass(frozen=True)
class HealthCheckResult:
    name: str
    status: str
    detail: str


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
    parser.add_argument("--page", choices=("map", "details", "crew", "loading", "error"), help="Render a single page and exit.")
    parser.add_argument("--offline", action="store_true", help="Skip live API calls and use cache/error paths only.")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer writes for safe verification.")
    parser.add_argument("--self-test", action="store_true", help="Run inline smoke tests and exit.")
    parser.add_argument("--health-check", action="store_true", help="Probe live NASA app endpoints and report endpoint health.")
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

def ensure_assets() -> None:
    required_assets = (
        MAP_TEMPLATE_PATH,
        MAP_STALE_TEMPLATE_PATH,
        DETAILS_TEMPLATE_PATH,
        CREW_TEMPLATE_PATH,
        CREW_STALE_TEMPLATE_PATH,
        ERROR_TEMPLATE_PATH,
        LOADING_TEMPLATE_PATH,
        DETAILS_GUIDE_PATH,
    )
    missing = [str(path) for path in required_assets if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required NASA assets: {', '.join(missing)}")



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


def fetch_json_value(url: str, *, timeout_secs: float = HTTP_TIMEOUT_SECS) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_secs) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_json(url: str, *, timeout_secs: float = HTTP_TIMEOUT_SECS) -> dict[str, Any]:
    payload = fetch_json_value(url, timeout_secs=timeout_secs)
    if not isinstance(payload, dict):
        raise ValueError("API response was not a JSON object")
    return payload


def fetch_json_list(url: str, *, timeout_secs: float = HTTP_TIMEOUT_SECS) -> list[Any]:
    payload = fetch_json_value(url, timeout_secs=timeout_secs)
    if not isinstance(payload, list):
        raise ValueError("API response was not a JSON list")
    return payload


def geoapify_api_key() -> str:
    raw_value = os.environ.get(GEOAPIFY_API_KEY_ENV, "").strip()
    if not raw_value:
        return ""
    parsed = urllib.parse.urlparse(raw_value)
    query = parsed.query if parsed.scheme or parsed.netloc else raw_value.lstrip("?")
    if "apikey=" in query.lower():
        values = urllib.parse.parse_qs(query)
        for key_name in ("apiKey", "apikey"):
            candidates = values.get(key_name)
            if candidates:
                candidate = candidates[0].strip()
                if candidate:
                    return candidate
    return raw_value


def fetch_geoapify_reverse_geocode(latitude: float, longitude: float, *, timeout_secs: float = HTTP_TIMEOUT_SECS) -> dict[str, Any]:
    api_key = geoapify_api_key()
    if not api_key:
        raise RuntimeError(f"{GEOAPIFY_API_KEY_ENV} is not configured")
    query = urllib.parse.urlencode(
        {
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "format": "json",
            "lang": "en",
            "apiKey": api_key,
        }
    )
    return fetch_json(f"{GEOAPIFY_REVERSE_URL}?{query}", timeout_secs=timeout_secs)


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


def coordinates_match(first: LocationSnapshot, second: LocationSnapshot, tolerance: float = 0.05) -> bool:
    return abs(first.latitude - second.latitude) <= tolerance and abs(first.longitude - second.longitude) <= tolerance


def compute_trail_timestamps(timestamp_value: int) -> list[int]:
    offsets = (-600, -450, -300, -150, 0, 150, 300, 450, 600)
    return [timestamp_value + offset for offset in offsets]


def fetch_trail(timestamp_value: int) -> list[OrbitPoint]:
    query = urllib.parse.urlencode({"timestamps": ",".join(str(item) for item in compute_trail_timestamps(timestamp_value))})
    payload = fetch_json_value(f"{WTIA_POSITIONS_URL}?{query}")
    if isinstance(payload, dict):
        points_raw = payload.get("positions", payload.get("data", payload))
    elif isinstance(payload, list):
        points_raw = payload
    else:
        raise ValueError("trail payload was neither a JSON object nor a list")
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


def build_open_notify_location(cached: LocationSnapshot | None) -> LocationSnapshot:
    payload = retry_call(lambda: fetch_json(OPEN_NOTIFY_ISS_URL))
    position = payload.get("iss_position", {})
    latitude = safe_float(position.get("latitude"))
    longitude = safe_float(position.get("longitude"))
    timestamp_value = safe_int(payload.get("timestamp")) or current_unix_time()
    if latitude is None or longitude is None:
        raise ValueError("open-notify payload is missing latitude/longitude")
    return LocationSnapshot(
        source="open-notify",
        fetched_at=current_unix_time(),
        position_timestamp=timestamp_value,
        latitude=latitude,
        longitude=longitude,
        altitude_km=cached.altitude_km if cached is not None else None,
        velocity_kmh=cached.velocity_kmh if cached is not None else None,
        country_code=cached.country_code if cached is not None else "",
        country_name=cached.country_name if cached is not None else "",
        location_label=cached.location_label if cached is not None else "",
        visibility=cached.visibility if cached is not None and cached.visibility else "TBA",
        trail=cached.trail if cached is not None else [],
        details_timestamp=cached.details_timestamp if cached is not None else timestamp_value,
    )


def first_geoapify_result(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                return item
    features = payload.get("features")
    if isinstance(features, list):
        for item in features:
            if not isinstance(item, dict):
                continue
            properties = item.get("properties")
            if isinstance(properties, dict):
                return properties
    raise ValueError("Geoapify response did not include a usable result")


def extract_geoapify_water_label(properties: dict[str, Any]) -> str:
    for key in ("formatted", "address_line1", "address_line2", "name"):
        value = clean_location_text(properties.get(key, ""))
        lowered = value.lower()
        if value and any(keyword in lowered for keyword in GEOAPIFY_AQUATIC_KEYWORDS):
            return value
    return ""


def resolve_geoapify_location(snapshot: LocationSnapshot, country_map: dict[str, str], cached: LocationSnapshot | None) -> tuple[str, str, str, bool]:
    try:
        geocode = retry_call(lambda: fetch_geoapify_reverse_geocode(snapshot.latitude, snapshot.longitude))
        properties = first_geoapify_result(geocode)
        country_code = clean_location_text(properties.get("country_code", ""), uppercase=True)
        country_name = clean_location_text(properties.get("country", "")) or iso_country_name(country_code, country_map)
        return country_code, country_name, extract_geoapify_water_label(properties), False
    except Exception:
        if cached is not None and coordinates_match(snapshot, cached):
            return (
                clean_location_text(cached.country_code, uppercase=True),
                clean_location_text(cached.country_name),
                clean_location_text(cached.location_label),
                True,
            )
        return "", "", "", True


def normalise_day_night(value: Any) -> str:
    lowered = str(value or "").strip().lower()
    if "day" in lowered:
        return "Day"
    if "night" in lowered or "eclips" in lowered:
        return "Night"
    return "Unknown"


def format_velocity(location: LocationSnapshot) -> str:
    if location.velocity_kmh is None:
        return "Unknown"
    return f"{location.velocity_kmh:,.0f} km/h"


def build_details_entries(location: LocationSnapshot) -> list[tuple[str, str]]:
    return [
        ("Longitude:", f"{location.longitude:.5f}"),
        ("Latitude:", f"{location.latitude:.5f}"),
        ("Currently over:", location_display_name(location)),
        ("Altitude:", f"{location.altitude_km:.0f} km" if location.altitude_km is not None else "Unknown"),
        ("Velocity:", format_velocity(location)),
        ("Day/Night:", normalise_day_night(location.visibility)),
    ]


def build_live_location(country_map: dict[str, str], cached: LocationSnapshot | None) -> tuple[LocationSnapshot, bool, bool]:
    now_ts = current_unix_time()
    sat_payload: dict[str, Any] | None = None

    try:
        snapshot = build_open_notify_location(cached)
    except Exception:
        sat_payload = retry_call(lambda: fetch_json(WTIA_SAT_URL))
        latitude = safe_float(sat_payload.get("latitude"))
        longitude = safe_float(sat_payload.get("longitude"))
        timestamp_value = safe_int(sat_payload.get("timestamp")) or now_ts
        if latitude is None or longitude is None:
            raise ValueError("live location payload is missing latitude/longitude")
        snapshot = LocationSnapshot(
            source="wheretheiss",
            fetched_at=now_ts,
            position_timestamp=timestamp_value,
            latitude=latitude,
            longitude=longitude,
            altitude_km=None,
            velocity_kmh=None,
            country_code=cached.country_code if cached is not None else "",
            country_name=cached.country_name if cached is not None else "",
            location_label=cached.location_label if cached is not None else "",
            visibility=cached.visibility if cached is not None and cached.visibility else "TBA",
            trail=cached.trail if cached is not None else [],
            details_timestamp=cached.details_timestamp if cached is not None else timestamp_value,
        )

    country_code = ""
    country_name = ""
    location_label = ""
    map_stale = False
    details_stale = False

    if sat_payload is None:
        try:
            sat_payload = retry_call(lambda: fetch_json(WTIA_SAT_URL))
        except Exception:
            sat_payload = None

    altitude_km = safe_float(sat_payload.get("altitude")) if sat_payload is not None else None
    velocity_kmh = safe_float(sat_payload.get("velocity")) if sat_payload is not None else None
    visibility = str(sat_payload.get("visibility", "")).strip().title() if sat_payload is not None else ""

    if altitude_km is None and cached is not None and cached.altitude_km is not None:
        altitude_km = cached.altitude_km
    if velocity_kmh is None and cached is not None and cached.velocity_kmh is not None:
        velocity_kmh = cached.velocity_kmh
    if not visibility and cached is not None and cached.visibility:
        visibility = cached.visibility
    if not visibility:
        visibility = "TBA"

    country_code, country_name, location_label, _geocode_stale = resolve_geoapify_location(snapshot, country_map, cached)

    try:
        trail = fetch_trail(snapshot.position_timestamp)
    except Exception:
        trail = cached.trail if cached is not None else []
        if trail:
            map_stale = True

    snapshot = LocationSnapshot(
        source=snapshot.source,
        fetched_at=snapshot.fetched_at,
        position_timestamp=snapshot.position_timestamp,
        latitude=snapshot.latitude,
        longitude=snapshot.longitude,
        altitude_km=altitude_km,
        velocity_kmh=velocity_kmh,
        country_code=country_code,
        country_name=country_name,
        location_label=location_label,
        visibility=visibility,
        trail=trail,
        details_timestamp=now_ts if sat_payload is not None else snapshot.details_timestamp,
    )
    return snapshot, map_stale, details_stale


def build_fallback_location(cached: LocationSnapshot | None) -> tuple[LocationSnapshot, bool, bool]:
    snapshot = build_open_notify_location(cached)
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


def paginate_crew(crew: list[CrewMember], page_size: int = 2) -> list[list[CrewMember]]:
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
    if country_name:
        return country_name
    if location_label:
        return location_label
    return "Unknown"


def draw_badge(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, *, fill: tuple[int, int, int], text_fill: tuple[int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=8, fill=fill)
    font = load_font(12, bold=True)
    draw.text((box[0] + 8, centred_text_y(font, label, (box[1] + box[3]) // 2)), label, font=font, fill=text_fill)


def draw_page_dots(draw: ImageDraw.ImageDraw, *, page_number: int, total_pages: int) -> None:
    if total_pages <= 1:
        return
    dot_diameter = 8
    gap = 8
    total_width = (total_pages * dot_diameter) + ((total_pages - 1) * gap)
    start_x = (CANVAS_WIDTH - total_width) // 2
    y = 214
    for index in range(total_pages):
        left = start_x + (index * (dot_diameter + gap))
        top = y
        fill = ACCENT_RGB if index + 1 == page_number else (70, 86, 108)
        draw.ellipse((left, top, left + dot_diameter, top + dot_diameter), fill=fill)


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


def render_details_page(location: LocationSnapshot, *, stale: bool) -> Image.Image:
    image = load_asset_candidates(DETAILS_TEMPLATE_PATH, ERROR_TEMPLATE_PATH)
    draw = ImageDraw.Draw(image)
    line_font = load_font(DETAILS_LABEL_FONT_SIZE, bold=False, name=DETAILS_LABEL_FONT_NAME)
    value_font = load_font(DETAILS_VALUE_FONT_SIZE, bold=False, name=DETAILS_VALUE_FONT_NAME)

    if stale:
        draw_badge(
            draw,
            overlay_bounds(DETAILS_STALE_BADGE_X, DETAILS_STALE_BADGE_Y, DETAILS_STALE_BADGE_WIDTH, DETAILS_STALE_BADGE_HEIGHT),
            "STALE",
            fill=(88, 64, 20),
            text_fill=TEXT_RGB,
        )

    entries = build_details_entries(location)
    row_centres = tuple(DETAILS_CONTENT_Y + (DETAILS_ROW_HEIGHT // 2) + (DETAILS_ROW_HEIGHT * index) for index in range(len(entries)))

    for (label, value), centre_y in zip(entries, row_centres):
        label_text = ellipsize_text(label, line_font, DETAILS_LABEL_WIDTH)
        value_text = ellipsize_text(str(value), value_font, DETAILS_VALUE_WIDTH)
        label_width = draw.textbbox((0, 0), label_text, font=line_font)[2]
        draw.text((DETAILS_LABEL_X + DETAILS_LABEL_WIDTH - label_width, centred_text_y(line_font, label_text, centre_y)), label_text, font=line_font, fill=TEXT_RGB)
        draw.text((DETAILS_VALUE_X, centred_text_y(value_font, value_text, centre_y)), value_text, font=value_font, fill=TEXT_RGB)
    return image

def render_crew_page(crew_page: list[CrewMember], page_number: int, total_pages: int, *, stale: bool) -> Image.Image:
    image = load_asset_candidates(CREW_STALE_TEMPLATE_PATH if stale else CREW_TEMPLATE_PATH, CREW_TEMPLATE_PATH, ERROR_TEMPLATE_PATH)
    draw = ImageDraw.Draw(image)
    name_font = load_font(CREW_NAME_FONT_SIZE, bold=True, name=CREW_NAME_FONT_NAME)
    detail_font = load_font(CREW_DETAIL_FONT_SIZE, bold=False, name=CREW_DETAIL_FONT_NAME)
    draw_page_dots(draw, page_number=page_number, total_pages=total_pages)
    if not crew_page:
        empty_text = "Crew data unavailable"
        width = draw.textbbox((0, 0), empty_text, font=detail_font)[2]
        draw.text(((CANVAS_WIDTH - width) // 2, 108), empty_text, font=detail_font, fill=TEXT_RGB)
        return image
    slots = tuple(zip(CREW_SLOT_NAME_CENTRES, CREW_SLOT_DETAIL_1_CENTRES, CREW_SLOT_DETAIL_2_CENTRES))
    for item, (name_y, detail_y1, detail_y2) in zip(crew_page, slots):
        name_text = ellipsize_text(item.name, name_font, CREW_CONTENT_WIDTH)
        detail_source = item.secondary or item.role or "ISS crew"
        detail_lines = wrap_text_lines(draw, detail_source, detail_font, CREW_CONTENT_WIDTH, 1)
        agency_line = compact_text(item.agency or item.spacecraft or "ISS crew", limit=40)
        name_x = CREW_CONTENT_X + max(0, (CREW_CONTENT_WIDTH - draw.textbbox((0, 0), name_text, font=name_font)[2]) // 2)
        draw.text((name_x, centred_text_y(name_font, name_text, name_y)), name_text, font=name_font, fill=TEXT_RGB)
        line_1 = detail_lines[0] if detail_lines else ""
        line_2 = agency_line
        if line_1:
            line_1_x = CREW_CONTENT_X + max(0, (CREW_CONTENT_WIDTH - draw.textbbox((0, 0), line_1, font=detail_font)[2]) // 2)
            draw.text((line_1_x, centred_text_y(detail_font, line_1, detail_y1)), line_1, font=detail_font, fill=(225, 225, 230))
        if line_2:
            line_2_x = CREW_CONTENT_X + max(0, (CREW_CONTENT_WIDTH - draw.textbbox((0, 0), line_2, font=detail_font)[2]) // 2)
            draw.text((line_2_x, centred_text_y(detail_font, line_2, detail_y2)), line_2, font=detail_font, fill=(225, 225, 230))
    return image


def render_error_page() -> Image.Image:
    image = load_asset_candidates(ERROR_TEMPLATE_PATH)
    draw = ImageDraw.Draw(image)
    title_font = load_font(16, bold=True)
    body_font = load_font(12, bold=False)
    draw.rounded_rectangle((34, 82, CANVAS_WIDTH - 34, 176), radius=16, fill=(14, 18, 38), outline=(237, 174, 82), width=2)
    draw.text((60, 98), "Startup failed", font=title_font, fill=(255, 222, 182))
    draw.text((49, 122), "No live ISS data and no usable", font=body_font, fill=TEXT_RGB)
    draw.text((64, 140), "cache was found.", font=body_font, fill=TEXT_RGB)
    draw.text((91, 159), "Retry later.", font=body_font, fill=(255, 198, 148))
    return image


def render_loading_page(stage: str = "position") -> Image.Image:
    image = load_asset_candidates(LOADING_TEMPLATE_PATH, MAP_TEMPLATE_PATH, DETAILS_TEMPLATE_PATH, ERROR_TEMPLATE_PATH)
    draw = ImageDraw.Draw(image)
    title_font = load_font(14, bold=True, name=DETAILS_TITLE_FONT_NAME)
    body_font = load_font(10, bold=False)
    title, body, foot = LOADING_STAGE_MESSAGES.get(stage, LOADING_STAGE_MESSAGES["position"])
    # notes: text box removed 30/03/2026; adjust these Y values to tighten or loosen the loading text stack.
    draw.text(((CANVAS_WIDTH - draw.textbbox((0, 0), title, font=title_font)[2]) // 2, 112), title, font=title_font, fill=(245, 245, 252))
    draw.text(((CANVAS_WIDTH - draw.textbbox((0, 0), body, font=body_font)[2]) // 2, 120), body, font=body_font, fill=(228, 230, 238))
    draw.text(((CANVAS_WIDTH - draw.textbbox((0, 0), foot, font=body_font)[2]) // 2, 128), foot, font=body_font, fill=(228, 230, 238))
    return image


def build_pages(location: LocationSnapshot | None, crew_snapshot: CrewSnapshot | None, *, map_stale: bool, details_stale: bool, crew_stale: bool) -> list[PageState]:
    if location is None:
        return [PageState(image=render_error_page(), kind="error", stale=False)]
    crew_pages = paginate_crew(crew_snapshot.crew if crew_snapshot is not None else [])
    total_crew_pages = max(1, len(crew_pages))
    pages = [
        PageState(image=render_map_page(location, stale=map_stale), kind="map", stale=map_stale),
        PageState(image=render_details_page(location, stale=details_stale), kind="details", stale=details_stale),
    ]
    for index, crew_page in enumerate(crew_pages, start=1):
        pages.append(PageState(image=render_crew_page(crew_page, index, total_crew_pages, stale=crew_stale), kind="crew", stale=crew_stale))
    return pages


def render_single_page(page_name: str, pages: list[PageState]) -> Image.Image:
    if page_name == "error":
        return render_error_page()
    if page_name == "loading":
        return render_loading_page("render")
    for page in pages:
        if page.kind == page_name:
            return page.image
    return pages[0].image


def build_health_check_result(name: str, status: str, detail: str) -> HealthCheckResult:
    return HealthCheckResult(name=name, status=status, detail=detail)


def probe_open_notify_position() -> tuple[HealthCheckResult, tuple[float, float, int] | None]:
    try:
        payload = fetch_json(OPEN_NOTIFY_ISS_URL)
        position = payload.get("iss_position", {})
        latitude = safe_float(position.get("latitude"))
        longitude = safe_float(position.get("longitude"))
        timestamp_value = safe_int(payload.get("timestamp")) or current_unix_time()
        if latitude is None or longitude is None:
            return build_health_check_result("open-notify-position", "degraded", "response missing latitude/longitude"), None
        return build_health_check_result("open-notify-position", "healthy", "current ISS position available"), (latitude, longitude, timestamp_value)
    except Exception as exc:
        return build_health_check_result("open-notify-position", "unavailable", str(exc)), None


def probe_wtia_satellite() -> tuple[HealthCheckResult, dict[str, Any] | None]:
    try:
        payload = fetch_json(WTIA_SAT_URL)
        latitude = safe_float(payload.get("latitude"))
        longitude = safe_float(payload.get("longitude"))
        altitude_km = safe_float(payload.get("altitude"))
        velocity_kmh = safe_float(payload.get("velocity"))
        if latitude is None or longitude is None:
            return build_health_check_result("wheretheiss-satellite", "degraded", "response missing latitude/longitude"), payload
        if altitude_km is None or velocity_kmh is None:
            return build_health_check_result("wheretheiss-satellite", "degraded", "position available but altitude/velocity incomplete"), payload
        return build_health_check_result("wheretheiss-satellite", "healthy", "position and enrichment fields available"), payload
    except Exception as exc:
        return build_health_check_result("wheretheiss-satellite", "unavailable", str(exc)), None


def probe_geoapify_reverse(latitude: float, longitude: float) -> HealthCheckResult:
    try:
        payload = fetch_geoapify_reverse_geocode(latitude, longitude)
        properties = first_geoapify_result(payload)
        country_name = clean_location_text(properties.get("country", ""))
        water_label = extract_geoapify_water_label(properties)
        if country_name:
            return build_health_check_result("geoapify-reverse", "healthy", f"country available: {country_name}")
        if water_label:
            return build_health_check_result("geoapify-reverse", "healthy", f"water label available: {water_label}")
        return build_health_check_result("geoapify-reverse", "degraded", "response missing country and water label")
    except Exception as exc:
        return build_health_check_result("geoapify-reverse", "unavailable", str(exc))


def probe_wtia_positions(timestamp_value: int) -> HealthCheckResult:
    try:
        trail = fetch_trail(timestamp_value)
        if trail:
            return build_health_check_result("wheretheiss-positions", "healthy", f"{len(trail)} trail points available")
        return build_health_check_result("wheretheiss-positions", "degraded", "endpoint responded without usable trail points")
    except Exception as exc:
        return build_health_check_result("wheretheiss-positions", "unavailable", str(exc))


def probe_crew_endpoint(name: str, fetcher) -> HealthCheckResult:
    try:
        crew, expedition, expedition_reason = fetcher()
        if not crew:
            return build_health_check_result(name, "degraded", "endpoint responded without ISS crew")
        if expedition or expedition_reason:
            return build_health_check_result(name, "healthy", f"{len(crew)} ISS crew entries available")
        return build_health_check_result(name, "degraded", f"{len(crew)} ISS crew entries available without expedition metadata")
    except Exception as exc:
        return build_health_check_result(name, "unavailable", str(exc))


def run_health_check() -> int:
    results: list[HealthCheckResult] = []
    open_notify_result, base_position = probe_open_notify_position()
    results.append(open_notify_result)
    satellite_result, sat_payload = probe_wtia_satellite()
    results.append(satellite_result)

    latitude: float | None = None
    longitude: float | None = None
    timestamp_value: int | None = None
    if base_position is not None:
        latitude, longitude, timestamp_value = base_position
    elif sat_payload is not None:
        latitude = safe_float(sat_payload.get("latitude"))
        longitude = safe_float(sat_payload.get("longitude"))
        timestamp_value = safe_int(sat_payload.get("timestamp")) or current_unix_time()

    if latitude is not None and longitude is not None:
        results.append(probe_geoapify_reverse(latitude, longitude))
    else:
        results.append(build_health_check_result("geoapify-reverse", "unavailable", "no usable live coordinates available"))

    if timestamp_value is not None:
        results.append(probe_wtia_positions(timestamp_value))
    else:
        results.append(build_health_check_result("wheretheiss-positions", "unavailable", "no usable live timestamp available"))

    results.append(probe_crew_endpoint("corquaid-crew", lambda: parse_corquaid_crew(fetch_json(CORQUAID_CREW_URL))))
    results.append(probe_crew_endpoint("open-notify-crew", lambda: parse_open_notify_crew(fetch_json(OPEN_NOTIFY_CREW_URL))))

    exit_code = 0
    for result in results:
        print(f"{result.name}: {result.status} - {result.detail}", flush=True)
        if result.status == "unavailable":
            exit_code = 1
    return exit_code

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
    if paginate_crew(sample_crew.crew, 2)[1][1].name != "Dina Example":
        print("[nasa] self-test failed: crew pagination mismatch", file=sys.stderr)
        return 1
    print("[nasa] self-test passed", flush=True)
    return 0

def run_preview(args: argparse.Namespace, country_map: dict[str, str]) -> int:
    if args.page == "loading":
        save_preview(render_loading_page("render"), args.output)
        return 0
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

    framebuffer = None
    if not args.no_framebuffer:
        if not Path(args.fbdev).exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        framebuffer = FramebufferWriter(args.fbdev, args.width, args.height)
        framebuffer.open()
        framebuffer.write_frame(render_loading_page("position").resize((args.width, args.height), RESAMPLING_LANCZOS))

    if framebuffer is not None:
        framebuffer.write_frame(render_loading_page("location").resize((args.width, args.height), RESAMPLING_LANCZOS))
    location, location_ok, map_stale, details_stale = resolve_location(country_map, location_path, args.offline)
    if framebuffer is not None:
        framebuffer.write_frame(render_loading_page("crew").resize((args.width, args.height), RESAMPLING_LANCZOS))
    crew_snapshot, crew_stale = resolve_crew(crew_path, args.offline)
    if framebuffer is not None:
        framebuffer.write_frame(render_loading_page("render").resize((args.width, args.height), RESAMPLING_LANCZOS))
    if not location_ok or location is None:
        pages = [PageState(image=render_error_page(), kind="error", stale=True)]
    else:
        pages = build_pages(location, crew_snapshot, map_stale=map_stale, details_stale=details_stale, crew_stale=crew_stale)
    if args.output and args.no_framebuffer:
        save_preview(pages[0].image, args.output)
        return 0

    touch_reader = TouchReader(args.width, args.height)
    page_index = 0
    last_rendered_index = -1
    ready_after = time.monotonic() + TOUCH_SETTLE_SECS
    next_refresh_at = time.monotonic() + LOCATION_REFRESH_SECS
    next_page_at = time.monotonic() + PAGE_CYCLE_SECS
    next_crew_refresh_at = time.monotonic()

    try:
        while not _STOP_REQUESTED:
            if page_index != last_rendered_index:
                image = pages[page_index].image.resize((args.width, args.height), RESAMPLING_LANCZOS)
                if framebuffer is not None:
                    framebuffer.write_frame(image)
                last_rendered_index = page_index

            now = time.monotonic()
            if now >= next_crew_refresh_at:
                crew_snapshot, crew_stale = resolve_crew(crew_path, args.offline)
                if location is not None:
                    pages = build_pages(location, crew_snapshot, map_stale=map_stale, details_stale=details_stale, crew_stale=crew_stale)
                page_index = min(page_index, len(pages) - 1)
                last_rendered_index = -1
                next_crew_refresh_at = now + LOCATION_REFRESH_SECS

            if now >= next_refresh_at:
                location, location_ok, map_stale, details_stale = resolve_location(country_map, location_path, args.offline)
                if location_ok and location is not None:
                    pages = build_pages(location, crew_snapshot, map_stale=map_stale, details_stale=details_stale, crew_stale=crew_stale)
                else:
                    pages = [PageState(image=render_error_page(), kind="error", stale=True)]
                page_index = min(page_index, len(pages) - 1)
                last_rendered_index = -1
                next_refresh_at = now + LOCATION_REFRESH_SECS

            if now >= next_page_at:
                page_index = (page_index + 1) % len(pages)
                next_page_at = now + PAGE_CYCLE_SECS

            wait_timeout = max(0.05, min(next_refresh_at - now, next_page_at - now, next_crew_refresh_at - now, 0.25))
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
    if args.health_check:
        return run_health_check()

    country_map = load_country_map()
    if args.page:
        return run_preview(args, country_map)
    return run_live(args, country_map)


if __name__ == "__main__":
    raise SystemExit(main())


