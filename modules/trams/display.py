#!/usr/bin/env python3
"""Render upcoming scheduled Metrolink departures for Firswood FIR1."""

from __future__ import annotations

import argparse
import json
import mmap
import os
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None

    class ZoneInfoNotFoundError(Exception):
        pass

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[1]
DEFAULT_CACHE_PATH = REPO_ROOT / "cache" / "tram_gtfs.json"
DEFAULT_ALERTS_CACHE_PATH = REPO_ROOT / "cache" / "tram_alerts.json"
DEFAULT_REFRESH_SCRIPT = MODULE_DIR / "tram_gtfs_refresh.py"
DEFAULT_TIMEZONE = os.environ.get("TRAM_TIMEZONE", "Europe/London")
FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
REFRESH_WAIT_SECS = 8.0


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


def rgb888_to_rgb565(image: Any) -> bytes:
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


def write_to_framebuffer(image: Any, fbdev: str, width: int, height: int) -> None:
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
    parser = argparse.ArgumentParser(description="Display scheduled Firswood town-centre Metrolink departures.")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE_PATH), help=f"GTFS cache path (default: {DEFAULT_CACHE_PATH})")
    parser.add_argument("--alerts-cache", default=str(DEFAULT_ALERTS_CACHE_PATH), help=f"Alerts cache path (default: {DEFAULT_ALERTS_CACHE_PATH})")
    parser.add_argument("--refresh-script", default=str(DEFAULT_REFRESH_SCRIPT), help=f"Refresh script (default: {DEFAULT_REFRESH_SCRIPT})")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
    parser.add_argument("--refresh-wait", type=float, default=REFRESH_WAIT_SECS, help="Seconds to wait after one refresh attempt.")
    parser.add_argument("--output", help="Optional output image path for local verification (PNG/JPG).")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer write (useful for local testing).")
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


def refresh_cache(refresh_script: Path) -> int:
    completed = subprocess.run([sys.executable, "-u", str(refresh_script)], check=False)
    return completed.returncode


def ensure_cache(
    cache_path: Path,
    refresh_script: Path,
    wait_secs: float,
    *,
    runner: Callable[[Path], int] = refresh_cache,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    if cache_path.exists():
        return True
    runner(refresh_script)
    sleeper(wait_secs)
    return cache_path.exists()


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
    weekday_name = (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    )[service_date.weekday()]
    return bool(weekdays.get(weekday_name))


def compute_upcoming_departures(cache: dict[str, Any], now: datetime, limit: int = 3) -> list[Departure]:
    timezone_name = str(cache.get("timezone", DEFAULT_TIMEZONE))
    tz = load_timezone(timezone_name)
    local_now = now.astimezone(tz)

    calendars = cache.get("service_calendar", {})
    departures = cache.get("departures", [])
    if not isinstance(calendars, dict) or not isinstance(departures, list):
        return []

    results: list[Departure] = []
    for offset in (-1, 0):
        service_date = local_now.date() + timedelta(days=offset)
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
            minutes = max(0, int((departure_dt - local_now).total_seconds() // 60))
            results.append(
                Departure(
                    headsign=headsign,
                    departure_time=departure_time,
                    departure_dt=departure_dt,
                    minutes=minutes,
                )
            )

    results.sort(key=lambda item: item.departure_dt)
    return results[:limit]


def _font(size: int, *, bold: bool = False) -> Any:
    from PIL import ImageFont

    env_name = "TRAM_FONT_PATH_BOLD" if bold else "TRAM_FONT_PATH"
    env_candidates = [entry.strip() for entry in os.getenv(env_name, "").split(",") if entry.strip()]
    defaults = (
        [
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
    )
    for candidate in env_candidates + defaults:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _fit_font(draw: Any, text: str, *, width_limit: int, initial_size: int, bold: bool = False) -> Any:
    size = initial_size
    while size >= 10:
        font = _font(size, bold=bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= width_limit:
            return font
        size -= 2
    return _font(10, bold=bold)


def _normalise_alert_items(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    cleaned: list[str] = []
    for entry in items:
        if isinstance(entry, str) and entry.strip():
            cleaned.append(entry.strip())
        elif isinstance(entry, dict):
            title = str(entry.get("title", "")).strip()
            if title:
                cleaned.append(title)
    return cleaned


def render_frame(
    cache: dict[str, Any] | None,
    alerts_cache: dict[str, Any] | None,
    now: datetime,
    width: int,
    height: int,
) -> Any:
    from PIL import Image, ImageDraw

    frame = Image.new("RGB", (width, height), (8, 26, 24))
    draw = ImageDraw.Draw(frame)

    panel = (20, 62, 55)
    accent = (255, 193, 7)
    mint = (180, 240, 220)
    white = (245, 248, 247)
    muted = (159, 191, 184)
    danger = (255, 140, 140)

    draw.rounded_rectangle((8, 8, width - 8, height - 8), radius=14, fill=panel, outline=(38, 101, 89), width=2)

    title_font = _font(22, bold=True)
    small_font = _font(12, bold=False)
    row_dest_font = _fit_font(draw, "Rochdale Town Centre", width_limit=178, initial_size=18, bold=True)
    row_time_font = _font(18, bold=True)
    ticker_font = _fit_font(draw, "No live tram alerts cached", width_limit=width - 28, initial_size=12, bold=False)

    draw.text((18, 16), "Firswood FIR1", font=title_font, fill=white)
    draw.text((18, 40), "Town centre departures", font=small_font, fill=mint)
    draw.text((width - 96, 18), now.strftime("%H:%M"), font=_font(26, bold=True), fill=accent)
    draw.text((width - 88, 44), now.strftime("%a %d %b"), font=small_font, fill=muted)

    departures = compute_upcoming_departures(cache or {}, now, limit=3) if cache else []
    generated_at = ""
    stop_name = "Firswood"
    if cache:
        generated_at = str(cache.get("generated_at", "")).strip()
        stop_name = str(cache.get("stop_name", stop_name)).strip() or stop_name

    top = 72
    row_height = 42
    if departures:
        for index, departure in enumerate(departures):
            row_top = top + (index * row_height)
            draw.rounded_rectangle((16, row_top, width - 16, row_top + 34), radius=10, fill=(14, 39, 35))
            draw.text((24, row_top + 6), departure.headsign, font=row_dest_font, fill=white)
            minute_text = "Due" if departure.minutes <= 0 else f"{departure.minutes}m"
            minute_x = width - 64
            draw.text((minute_x, row_top + 6), minute_text, font=row_time_font, fill=accent)
            draw.text((minute_x - 26, row_top + 21), departure.departure_dt.strftime("%H:%M"), font=small_font, fill=muted)
    else:
        message = "GTFS cache unavailable"
        detail = "Run tram_gtfs_refresh.py"
        if cache:
            message = "No more scheduled departures"
            detail = "for the current service day"
        draw.rounded_rectangle((16, 84, width - 16, 156), radius=12, fill=(14, 39, 35))
        draw.text((24, 102), message, font=_fit_font(draw, message, width_limit=width - 48, initial_size=22, bold=True), fill=danger if not cache else white)
        draw.text((24, 131), detail, font=small_font, fill=muted)

    status_line = stop_name
    if generated_at:
        status_line = f"{stop_name}  cache {generated_at[11:16]}"
    draw.text((18, 194), status_line, font=small_font, fill=muted)

    alert_items = _normalise_alert_items(alerts_cache)
    ticker_text = "No live tram alerts cached"
    ticker_fill = muted
    if alert_items:
        ticker_text = " | ".join(alert_items[:2])
        ticker_fill = white
    elif alerts_cache and str(alerts_cache.get("message", "")).strip():
        ticker_text = str(alerts_cache.get("message", "")).strip()
    draw.rounded_rectangle((14, 208, width - 14, height - 14), radius=10, fill=(13, 33, 30))
    draw.text((22, 216), ticker_text, font=ticker_font, fill=ticker_fill)
    return frame


def run_self_tests() -> int:
    tz = load_timezone("Europe/London")
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
            {"service_id": "WK", "headsign": "Rochdale Town Centre", "departure_time": "25:03:00", "departure_secs": 25 * 3600 + 3 * 60},
        ],
    }
    monday = date(2026, 3, 16)
    if not service_runs_on(cache["service_calendar"]["WK"], monday):
        raise AssertionError("weekday service should be valid on Monday")

    now = datetime(2026, 3, 16, 8, 0, tzinfo=tz)
    upcoming = compute_upcoming_departures(cache, now, limit=3)
    if [item.headsign for item in upcoming] != ["Victoria", "Rochdale Town Centre"]:
        raise AssertionError("departures should be ordered chronologically")

    overnight_now = datetime(2026, 3, 17, 0, 30, tzinfo=tz)
    overnight = compute_upcoming_departures(cache, overnight_now, limit=3)
    if not overnight or overnight[0].headsign != "Rochdale Town Centre" or overnight[0].departure_dt.hour != 1:
        raise AssertionError("after-midnight departures from previous service day should still appear first")
    output = render_frame(cache, {"items": ["Service change at Cornbrook"]}, now, 320, 240)
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
    if args.refresh_wait < 0:
        print("Refresh wait cannot be negative.", file=sys.stderr)
        return 1

    cache_path = Path(args.cache)
    refresh_script = Path(args.refresh_script)
    ensure_cache(cache_path, refresh_script, args.refresh_wait)
    cache = load_json(cache_path)
    alerts_cache = load_json(Path(args.alerts_cache))
    tz = load_timezone(str(cache.get("timezone", DEFAULT_TIMEZONE)) if cache else DEFAULT_TIMEZONE)
    frame = render_frame(cache, alerts_cache, datetime.now(tz=tz), args.width, args.height)

    if args.output:
        frame.save(args.output)
        print(f"Saved preview image to {args.output}")

    if args.no_framebuffer:
        print("Skipping framebuffer write (--no-framebuffer set)")
        return 0

    fb_path = Path(args.fbdev)
    if not fb_path.exists():
        print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
        return 1

    write_to_framebuffer(frame, args.fbdev, args.width, args.height)
    print(f"Displayed tram departures on {args.fbdev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


