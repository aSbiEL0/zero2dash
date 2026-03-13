#!/usr/bin/env python3
"""Render the live Firswood tram page over the tram background asset."""

from __future__ import annotations

import argparse
import json
import mmap
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None

    class ZoneInfoNotFoundError(Exception):
        pass

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE_PATH = MODULE_DIR / "tram_timetable.json"
DEFAULT_ALERTS_CACHE_PATH = MODULE_DIR / "tram_alerts.json"
DEFAULT_BACKGROUND_PATH = MODULE_DIR / "tram-background.png"
DEFAULT_TIMEZONE = os.environ.get("TRAM_TIMEZONE", "Europe/London")
FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
FRAME_DELAY_DEFAULT = 0.02
TICKER_SPEED_DEFAULT = 24.0
ALERT_ROTATION_SECS = 15
WEEKDAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_STOP_REQUESTED = False


@dataclass(frozen=True)
class Departure:
    headsign: str
    departure_time: str
    departure_dt: datetime
    minutes: int


def load_timezone(name: str):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            pass
    if name in {"Europe/London", "UTC"}:
        return timezone.utc
    raise ValueError(f"Timezone data unavailable for {name!r}; install tzdata or use a host with IANA timezone support")


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

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Display live Firswood tram departures.")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE_PATH), help=f"Timetable cache path (default: {DEFAULT_CACHE_PATH})")
    parser.add_argument("--alerts-cache", default=str(DEFAULT_ALERTS_CACHE_PATH), help=f"Alerts cache path (default: {DEFAULT_ALERTS_CACHE_PATH})")
    parser.add_argument("--background", default=str(DEFAULT_BACKGROUND_PATH), help=f"Background image path (default: {DEFAULT_BACKGROUND_PATH})")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
    parser.add_argument("--output", help="Optional output image path for local verification (PNG/JPG).")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer writes.")
    parser.add_argument("--frames", type=int, default=0, help="Number of frames to render before exiting; 0 means run until terminated.")
    parser.add_argument("--frame-delay", type=float, default=FRAME_DELAY_DEFAULT, help="Seconds between animation frames.")
    parser.add_argument("--ticker-speed", type=float, default=TICKER_SPEED_DEFAULT, help="Ticker speed in pixels per second.")
    parser.add_argument("--frame-log", action="store_true", help="Log achieved frame rate once per second.")
    parser.add_argument("--self-test", action="store_true", help="Run inline smoke tests and exit.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def service_runs_on(service: dict[str, Any], service_date: date) -> bool:
    removed_dates = set(service.get("removed_dates", []))
    added_dates = set(service.get("added_dates", []))
    iso_value = service_date.isoformat()
    if iso_value in removed_dates:
        return False
    if iso_value in added_dates:
        return True
    start_date = service.get("start_date")
    end_date = service.get("end_date")
    if not isinstance(start_date, str) or not isinstance(end_date, str):
        return False
    if iso_value < start_date or iso_value > end_date:
        return False
    weekdays = service.get("weekdays", {})
    if not isinstance(weekdays, dict):
        return False
    return bool(weekdays.get(WEEKDAY_NAMES[service_date.weekday()]))


def compute_upcoming_departures(cache: dict[str, Any], now: datetime, limit: int = 4) -> list[Departure]:
    timezone_name = str(cache.get("timezone", DEFAULT_TIMEZONE))
    tz = load_timezone(timezone_name)
    local_now = now.astimezone(tz)
    calendars = cache.get("service_calendar", {})
    departures = cache.get("departures", [])
    if not isinstance(calendars, dict) or not isinstance(departures, list):
        return []
    service_date = local_now.date()
    results: list[Departure] = []
    for item in departures:
        if not isinstance(item, dict):
            continue
        service_id = str(item.get("service_id", ""))
        headsign = str(item.get("headsign", "")).strip()
        departure_time = str(item.get("departure_time", "")).strip()
        departure_secs = item.get("departure_secs")
        service = calendars.get(service_id)
        if not service or not headsign or not departure_time or not isinstance(departure_secs, int):
            continue
        if not service_runs_on(service, service_date):
            continue
        departure_dt = datetime.combine(service_date, dt_time.min, tzinfo=tz) + timedelta(seconds=departure_secs)
        if departure_dt < local_now:
            continue
        results.append(Departure(headsign=headsign, departure_time=departure_time, departure_dt=departure_dt, minutes=max(0, int((departure_dt - local_now).total_seconds() // 60))))
    results.sort(key=lambda item: item.departure_dt)
    return results[:limit]


@lru_cache(maxsize=32)
def _font(size: int, *, bold: bool = False, italic: bool = False):
    env_name = "TRAM_FONT_PATH_BOLD" if bold else "TRAM_FONT_PATH_ITALIC" if italic else "TRAM_FONT_PATH"
    env_candidates = [entry.strip() for entry in os.getenv(env_name, "").split(",") if entry.strip()]
    defaults = {
        (False, False): [
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ],
        (True, False): [
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ],
        (False, True): [
            "/usr/share/fonts/truetype/noto/NotoSans-Italic.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansOblique.ttf",
        ],
    }
    for candidate in env_candidates + defaults[(bold, italic)]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _text_width(text: str, font: ImageFont.ImageFont | ImageFont.FreeTypeFont) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


@lru_cache(maxsize=128)
def _fit_font(text: str, *, width_limit: int, initial_size: int, min_size: int, bold: bool = False, italic: bool = False):
    size = initial_size
    while size >= min_size:
        font = _font(size, bold=bold, italic=italic)
        if _text_width(text, font) <= width_limit:
            return font
        size -= 1
    return _font(min_size, bold=bold, italic=italic)


def _ellipsize_text(text: str, font: ImageFont.ImageFont | ImageFont.FreeTypeFont, width_limit: int) -> str:
    if _text_width(text, font) <= width_limit:
        return text
    suffix = '...'
    available = width_limit - _text_width(suffix, font)
    if available <= 0:
        return suffix
    trimmed = text
    while trimmed and _text_width(trimmed, font) > available:
        trimmed = trimmed[:-1].rstrip()
    return f"{trimmed}{suffix}" if trimmed else suffix

def _cache_status(cache: dict[str, Any] | None) -> str:
    if cache is None:
        return "missing"
    if not isinstance(cache.get("departures"), list) or not isinstance(cache.get("service_calendar"), dict):
        return "invalid"
    return "ok"


def _alert_texts_from_cache(alerts_cache: dict[str, Any] | None) -> list[str] | None:
    if alerts_cache is None or not isinstance(alerts_cache.get("items"), list):
        return None
    texts: list[str] = []
    for item in alerts_cache["items"]:
        if isinstance(item, dict):
            text = str(item.get("ticker_text", "") or item.get("title", "")).strip()
        else:
            text = str(item).strip()
        if text:
            texts.append(text)
    return texts


def ticker_text_from_alerts(alerts_cache: dict[str, Any] | None, *, now: datetime | None = None) -> str:
    texts = _alert_texts_from_cache(alerts_cache)
    if texts is None:
        return "Alerts unavailable"
    if not texts:
        return "No current tram alerts"
    if len(texts) == 1:
        return texts[0]
    current = now or datetime.now(timezone.utc)
    rotation_slot = int(current.timestamp() // ALERT_ROTATION_SECS)
    return texts[rotation_slot % len(texts)]

def load_background(path: Path, width: int, height: int) -> Image.Image:
    if path.exists():
        return Image.open(path).convert("RGB").resize((width, height))
    return Image.new("RGB", (width, height), (0, 0, 0))


def render_static_frame(background: Image.Image, cache: dict[str, Any] | None, now: datetime) -> Image.Image:
    frame = background.copy()
    draw = ImageDraw.Draw(frame)
    width, _height = frame.size
    white = (245, 245, 245)
    departures = compute_upcoming_departures(cache or {}, now, limit=3) if _cache_status(cache) == "ok" else []
    body_font = _fit_font("Rochdale Town Centre", width_limit=210, initial_size=22, min_size=12)                    #Tram line font size
    mins_font = _fit_font("27min", width_limit=72, initial_size=22, min_size=12)                                    #Time left font size
    message_font = _fit_font("Timetable unavailable", width_limit=280, initial_size=24, min_size=13)
    top = 92
    row_height = 26
    status = _cache_status(cache)
    if status != "ok":
        draw.text((24, top), "Timetable unavailable", font=message_font, fill=white)
    elif not departures:
        draw.text((24, top), "No more trams today", font=message_font, fill=white)
    else:
        for index, departure in enumerate(departures):
            y = top + (index * row_height)
            headsign_text = _ellipsize_text(departure.headsign, body_font, 170)
            draw.text((22, y), headsign_text, font=body_font, fill=white)
            minute_text = "Due" if departure.minutes <= 0 else f"{departure.minutes}min"
            draw.text((width - 22 - _text_width(minute_text, mins_font), y), minute_text, font=mins_font, fill=white)
    return frame


def ticker_region_top(height: int) -> int:
    return max(0, height - 52)


def render_ticker_strip(base_frame: Image.Image, alerts_cache: dict[str, Any] | None, *, ticker_offset: float = 0.0) -> tuple[Image.Image, int]:
    width, height = base_frame.size
    strip_top = ticker_region_top(height)
    strip = base_frame.crop((0, strip_top, width, height))
    draw = ImageDraw.Draw(strip)
    white = (245, 245, 245)
    amber = (244, 198, 0)
    ticker_text = ticker_text_from_alerts(alerts_cache)
    ticker_font = _fit_font(ticker_text, width_limit=max(160, width - 30), initial_size=26, min_size=22, italic=True)   #Ticker font size
    baseline_y = (height - 34) - strip_top
    text_width = _text_width(ticker_text, ticker_font)
    ticker_fill = amber if ticker_text == "Alerts unavailable" else white
    if text_width > width - 44:
        loop_width = text_width + 48
        x = 26 - (ticker_offset % loop_width)
        while x < width:
            draw.text((x, baseline_y), ticker_text, font=ticker_font, fill=ticker_fill)
            x += loop_width
    else:
        draw.text((22, baseline_y), ticker_text, font=ticker_font, fill=ticker_fill)
    return strip, strip_top


def render_frame(background: Image.Image, cache: dict[str, Any] | None, alerts_cache: dict[str, Any] | None, now: datetime, *, ticker_offset: float = 0.0) -> Image.Image:
    frame = render_static_frame(background, cache, now)
    strip, strip_top = render_ticker_strip(frame, alerts_cache, ticker_offset=ticker_offset)
    frame.paste(strip, (0, strip_top))
    return frame


def _handle_stop_request(_signum: int, _frame: object) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def run_self_tests() -> int:
    background = Image.new("RGB", (320, 240), (0, 0, 0))
    cache = {
        "timezone": "Europe/London",
        "service_calendar": {
            "WK": {
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "weekdays": {
                    "monday": True,
                    "tuesday": True,
                    "wednesday": True,
                    "thursday": True,
                    "friday": True,
                    "saturday": False,
                    "sunday": False,
                },
                "added_dates": [],
                "removed_dates": [],
            }
        },
        "departures": [
            {"service_id": "WK", "headsign": "Victoria", "departure_time": "08:12:00", "departure_secs": 8 * 3600 + 12 * 60},
            {"service_id": "WK", "headsign": "Rochdale Town Centre", "departure_time": "09:03:00", "departure_secs": 9 * 3600 + 3 * 60},
        ],
    }
    now = datetime(2026, 3, 16, 8, 0, tzinfo=load_timezone("Europe/London"))
    upcoming = compute_upcoming_departures(cache, now, limit=4)
    if [item.headsign for item in upcoming] != ["Victoria", "Rochdale Town Centre"]:
        raise AssertionError("departures should be ordered chronologically")
    if ticker_text_from_alerts(None) != "Alerts unavailable":
        raise AssertionError("missing cache should report alerts unavailable")
    if ticker_text_from_alerts({"items": []}) != "No current tram alerts":
        raise AssertionError("empty cache should report no current alerts")
    output = render_frame(background, cache, {"items": [{"ticker_text": "Service change at Cornbrook"}]}, now, ticker_offset=12)
    if output.size != (320, 240):
        raise AssertionError("rendered frame dimensions should match request")
    print("[trams/display.py] Self tests passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_tests()
    if args.width <= 0 or args.height <= 0:
        print("Width/height must be positive integers.", file=sys.stderr)
        return 1
    if args.frame_delay < 0:
        print("Frame delay cannot be negative.", file=sys.stderr)
        return 1
    if args.ticker_speed < 0:
        print("Ticker speed cannot be negative.", file=sys.stderr)
        return 1
    signal.signal(signal.SIGTERM, _handle_stop_request)
    signal.signal(signal.SIGINT, _handle_stop_request)
    background = load_background(Path(args.background), args.width, args.height)
    cache = load_json(Path(args.cache))
    alerts_cache = load_json(Path(args.alerts_cache))
    tz = load_timezone(str((cache or {}).get("timezone", DEFAULT_TIMEZONE)))
    framebuffer: FramebufferWriter | None = None
    if not args.no_framebuffer:
        fb_path = Path(args.fbdev)
        if not fb_path.exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        framebuffer = FramebufferWriter(args.fbdev, args.width, args.height)
        framebuffer.open()
    startup_now = datetime.now(tz=tz)
    static_frame = render_static_frame(background, cache, startup_now)
    if framebuffer is not None:
        framebuffer.write_frame(static_frame)
    animation_start = time.monotonic()
    frame_index = 0
    saved_output = False
    stats_window_start = animation_start
    stats_render_ms = 0.0
    stats_framebuffer_ms = 0.0
    stats_frame_count = 0
    try:
        while not _STOP_REQUESTED:
            frame_started = time.monotonic()
            elapsed = frame_started - animation_start
            ticker_offset = elapsed * args.ticker_speed
            ticker_strip, ticker_top = render_ticker_strip(static_frame, alerts_cache, ticker_offset=ticker_offset)
            stats_render_ms += (time.monotonic() - frame_started) * 1000
            if args.output and not saved_output:
                frame = static_frame.copy()
                frame.paste(ticker_strip, (0, ticker_top))
                frame.save(args.output)
                print(f"Saved preview image to {args.output}")
                saved_output = True
            if framebuffer is not None:
                framebuffer_started = time.monotonic()
                framebuffer.write_region(ticker_strip, 0, ticker_top)
                stats_framebuffer_ms += (time.monotonic() - framebuffer_started) * 1000
            frame_index += 1
            stats_frame_count += 1
            if args.frame_log:
                stats_elapsed = time.monotonic() - stats_window_start
                if stats_elapsed >= 1.0:
                    fps = stats_frame_count / stats_elapsed
                    avg_frame_ms = (stats_elapsed / stats_frame_count) * 1000 if stats_frame_count else 0.0
                    avg_render_ms = stats_render_ms / stats_frame_count if stats_frame_count else 0.0
                    avg_framebuffer_ms = stats_framebuffer_ms / stats_frame_count if stats_frame_count else 0.0
                    print(f"[frame-log] fps={fps:.1f} avg_frame_ms={avg_frame_ms:.1f} render_ms={avg_render_ms:.1f} framebuffer_ms={avg_framebuffer_ms:.1f} ticker_speed={args.ticker_speed:.1f}")
                    stats_window_start = time.monotonic()
                    stats_frame_count = 0
                    stats_render_ms = 0.0
                    stats_framebuffer_ms = 0.0
            if args.frames > 0 and frame_index >= args.frames:
                break
            time.sleep(args.frame_delay)
    finally:
        if framebuffer is not None:
            framebuffer.close()
    if args.no_framebuffer:
        print("Skipping framebuffer write (--no-framebuffer set)")
    else:
        print(f"Displayed tram departures on {args.fbdev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())




