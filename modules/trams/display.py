#!/usr/bin/env python3
"""Render the live Firswood tram page over the tram background asset."""

from __future__ import annotations

import argparse
import json
import mmap
import os
import signal
import struct
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
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
TICKER_SPEED_DEFAULT = 350.0
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


def write_to_framebuffer(image: Image.Image, fbdev: str, width: int, height: int) -> None:
    payload = rgb888_to_rgb565(image)
    expected = width * height * 2
    if len(payload) != expected:
        raise RuntimeError(f"Framebuffer payload size mismatch: expected {expected} bytes, got {len(payload)} bytes")
    with open(fbdev, "r+b", buffering=0) as framebuffer:
        mm = mmap.mmap(framebuffer.fileno(), expected, mmap.MAP_SHARED, mmap.PROT_WRITE)
        mm.seek(0)
        mm.write(payload)
        mm.close()


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


def _fit_font(draw: ImageDraw.ImageDraw, text: str, *, width_limit: int, initial_size: int, min_size: int, bold: bool = False, italic: bool = False):
    size = initial_size
    while size >= min_size:
        font = _font(size, bold=bold, italic=italic)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= width_limit:
            return font
        size -= 1
    return _font(min_size, bold=bold, italic=italic)


def _cache_status(cache: dict[str, Any] | None) -> str:
    if cache is None:
        return "missing"
    if not isinstance(cache.get("departures"), list) or not isinstance(cache.get("service_calendar"), dict):
        return "invalid"
    return "ok"


def ticker_text_from_alerts(alerts_cache: dict[str, Any] | None) -> str:
    if alerts_cache is None or not isinstance(alerts_cache.get("items"), list):
        return "Alerts unavailable"
    if not alerts_cache["items"]:
        return "No current tram alerts"
    texts: list[str] = []
    for item in alerts_cache["items"]:
        if isinstance(item, dict):
            text = str(item.get("ticker_text", "") or item.get("title", "")).strip()
        else:
            text = str(item).strip()
        if text:
            texts.append(text)
    return "   |   ".join(texts) if texts else "No current tram alerts"


def load_background(path: Path, width: int, height: int) -> Image.Image:
    if path.exists():
        return Image.open(path).convert("RGB").resize((width, height))
    return Image.new("RGB", (width, height), (0, 0, 0))


def render_frame(background: Image.Image, cache: dict[str, Any] | None, alerts_cache: dict[str, Any] | None, now: datetime, *, ticker_offset: float = 0.0) -> Image.Image:
    frame = background.copy()
    draw = ImageDraw.Draw(frame)
    width, height = frame.size
    white = (245, 245, 245)
    amber = (244, 198, 0)
    departures = compute_upcoming_departures(cache or {}, now, limit=4) if _cache_status(cache) == "ok" else []
    body_font = _fit_font(draw, "Rochdale Town Centre", width_limit=210, initial_size=18, min_size=12)
    mins_font = _fit_font(draw, "27min", width_limit=72, initial_size=18, min_size=12)
    message_font = _fit_font(draw, "Timetable unavailable", width_limit=280, initial_size=18, min_size=13)
    ticker_text = ticker_text_from_alerts(alerts_cache)
    ticker_font = _fit_font(draw, ticker_text, width_limit=max(160, width - 30), initial_size=22, min_size=18, italic=True)
    top = 92
    row_height = 24
    status = _cache_status(cache)
    if status != "ok":
        draw.text((22, top), "Timetable unavailable", font=message_font, fill=white)
    elif not departures:
        draw.text((22, top), "No more trams today", font=message_font, fill=white)
    else:
        for index, departure in enumerate(departures):
            y = top + (index * row_height)
            draw.text((22, y), departure.headsign, font=body_font, fill=white)
            minute_text = "Due" if departure.minutes <= 0 else f"{departure.minutes}min"
            bbox = draw.textbbox((0, 0), minute_text, font=mins_font)
            draw.text((width - 22 - (bbox[2] - bbox[0]), y), minute_text, font=mins_font, fill=white)
    baseline_y = height - 34
    text_bbox = draw.textbbox((0, 0), ticker_text, font=ticker_font)
    text_width = text_bbox[2] - text_bbox[0]
    ticker_fill = amber if ticker_text == "Alerts unavailable" else white
    if text_width > width - 44:
        loop_width = text_width + 48
        x = 22 - (ticker_offset % loop_width)
        while x < width:
            draw.text((x, baseline_y), ticker_text, font=ticker_font, fill=ticker_fill)
            x += loop_width
    else:
        draw.text((22, baseline_y), ticker_text, font=ticker_font, fill=ticker_fill)
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
    animation_start = time.monotonic()
    frame_index = 0
    saved_output = False
    while not _STOP_REQUESTED:
        now = datetime.now(tz=tz)
        elapsed = time.monotonic() - animation_start
        ticker_offset = elapsed * args.ticker_speed
        frame = render_frame(background, cache, alerts_cache, now, ticker_offset=ticker_offset)
        if args.output and not saved_output:
            frame.save(args.output)
            print(f"Saved preview image to {args.output}")
            saved_output = True
        if not args.no_framebuffer:
            fb_path = Path(args.fbdev)
            if not fb_path.exists():
                print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
                return 1
            write_to_framebuffer(frame, args.fbdev, args.width, args.height)
        frame_index += 1
        if args.frames > 0 and frame_index >= args.frames:
            break
        time.sleep(args.frame_delay)
    if args.no_framebuffer:
        print("Skipping framebuffer write (--no-framebuffer set)")
    else:
        print(f"Displayed tram departures on {args.fbdev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
