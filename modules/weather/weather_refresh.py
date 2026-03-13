#!/usr/bin/env python3
"""Fetch current weather data and render a 320x240 dashboard image."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None

    class ZoneInfoNotFoundError(Exception):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _config import get_env, report_validation_errors

DEFAULT_ROOT = Path("~/zero2dash").expanduser()
SCRIPT_NAME = "weather_refresh.py"
MODULE_DIR = SCRIPT_DIR
DEFAULT_OUTPUT_PATH = MODULE_DIR / "weather.png"
DEFAULT_CACHE_PATH = MODULE_DIR / "weather-cache.json"
DEFAULT_BACKGROUND_PATH = MODULE_DIR / "weather-background.png"
DEFAULT_API_BASE = "https://api.open-meteo.com/v1/forecast"
CANVAS_WIDTH = 320
CANVAS_HEIGHT = 240
TEXT_COLOUR = (245, 245, 245)
FALLBACK_BACKGROUND = (0, 0, 0)


@dataclass(frozen=True)
class Config:
    lat: float
    lon: float
    label: str
    timezone_name: str
    timeout_secs: float
    api_base: str
    output_path: Path
    cache_path: Path
    background_path: Path


@dataclass(frozen=True)
class WeatherSnapshot:
    location: str
    temperature_c: int
    wind_kmh: int
    rain_probability: int
    max_temp_c: int
    min_temp_c: int
    observed_at: str
    timezone_name: str


def load_timezone(name: str):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            pass
    if name in {"Europe/London", "UTC"}:
        return timezone.utc
    raise ValueError(f"Timezone data unavailable for {name!r}; install tzdata or use a host with IANA timezone support")


def parse_lat(value: str) -> float:
    parsed = float(value)
    if parsed < -90.0 or parsed > 90.0:
        raise ValueError("must be between -90 and 90")
    return parsed


def parse_lon(value: str) -> float:
    parsed = float(value)
    if parsed < -180.0 or parsed > 180.0:
        raise ValueError("must be between -180 and 180")
    return parsed


def parse_timeout(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("must be greater than 0")
    return parsed


def expand_path(raw_value: str, default: Path) -> Path:
    candidate = Path(raw_value).expanduser() if raw_value else default
    return candidate if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()


def validate_config() -> tuple[Config | None, list[str]]:
    errors: list[str] = []

    def record(name: str, *, default: Any = None, required: bool = False, validator=None):
        try:
            return get_env(name, default=default, required=required, validator=validator)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    lat = record("WEATHER_LAT", required=True, validator=parse_lat)
    lon = record("WEATHER_LON", required=True, validator=parse_lon)
    label = str(record("WEATHER_LABEL", default="Weather")).strip() or "Weather"
    timezone_name = str(record("WEATHER_TIMEZONE", default="Europe/London")).strip() or "Europe/London"
    timeout_secs = record("WEATHER_API_TIMEOUT", default=5.0, validator=parse_timeout)
    api_base = str(record("WEATHER_API_BASE", default=DEFAULT_API_BASE)).strip() or DEFAULT_API_BASE
    output_path = expand_path(str(record("WEATHER_OUTPUT_PATH", default=str(DEFAULT_OUTPUT_PATH))), DEFAULT_OUTPUT_PATH)
    cache_path = expand_path(str(record("WEATHER_CACHE_PATH", default=str(DEFAULT_CACHE_PATH))), DEFAULT_CACHE_PATH)
    background_path = expand_path(str(record("WEATHER_BACKGROUND_PATH", default=str(DEFAULT_BACKGROUND_PATH))), DEFAULT_BACKGROUND_PATH)

    try:
        load_timezone(timezone_name)
    except ValueError as exc:
        errors.append(f"WEATHER_TIMEZONE is invalid: {exc}")

    if errors:
        return None, errors

    return Config(
        lat=float(lat),
        lon=float(lon),
        label=label,
        timezone_name=timezone_name,
        timeout_secs=float(timeout_secs),
        api_base=api_base,
        output_path=output_path,
        cache_path=cache_path,
        background_path=background_path,
    ), []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch weather data and render the weather module image.")
    parser.add_argument("--check-config", action="store_true", help="Validate env configuration and exit.")
    parser.add_argument("--output", help="Override output image path for local verification.")
    parser.add_argument("--self-test", action="store_true", help="Run inline smoke tests and exit.")
    return parser.parse_args()


def build_api_url(config: Config) -> str:
    query = urllib.parse.urlencode(
        {
            "latitude": f"{config.lat:.6f}",
            "longitude": f"{config.lon:.6f}",
            "current": "temperature_2m,wind_speed_10m",
            "hourly": "precipitation_probability",
            "daily": "temperature_2m_max,temperature_2m_min",
            "forecast_days": "1",
            "timezone": config.timezone_name,
        }
    )
    return f"{config.api_base}?{query}"


def fetch_weather_payload(config: Config) -> dict[str, Any]:
    request = urllib.request.Request(
        build_api_url(config),
        headers={"User-Agent": "zero2dash-weather/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=config.timeout_secs) as response:
        return json.loads(response.read().decode("utf-8"))


def _round_int(value: Any) -> int:
    return int(round(float(value)))


def select_hourly_value(times: list[Any], values: list[Any], target_time: datetime) -> int:
    target_hour = target_time.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:00")
    for index, raw_time in enumerate(times):
        if str(raw_time) == target_hour and index < len(values):
            return max(0, _round_int(values[index]))
    return 0


def parse_weather_payload(payload: dict[str, Any], *, location_label: str, fallback_time: datetime) -> WeatherSnapshot:
    current = payload.get("current")
    hourly = payload.get("hourly")
    daily = payload.get("daily")
    timezone_name = str(payload.get("timezone") or fallback_time.tzinfo or "UTC")

    if not isinstance(current, dict) or not isinstance(hourly, dict) or not isinstance(daily, dict):
        raise ValueError("payload is missing current/hourly/daily weather sections")

    current_time_raw = str(current.get("time", "")).strip()
    current_time = datetime.fromisoformat(current_time_raw) if current_time_raw else fallback_time
    rain_probability = select_hourly_value(
        list(hourly.get("time", [])),
        list(hourly.get("precipitation_probability", [])),
        current_time,
    )

    daily_times = list(daily.get("time", []))
    max_values = list(daily.get("temperature_2m_max", []))
    min_values = list(daily.get("temperature_2m_min", []))
    if not daily_times or not max_values or not min_values:
        raise ValueError("payload is missing daily temperature values")

    return WeatherSnapshot(
        location=location_label,
        temperature_c=_round_int(current["temperature_2m"]),
        wind_kmh=_round_int(current["wind_speed_10m"]),
        rain_probability=rain_probability,
        max_temp_c=_round_int(max_values[0]),
        min_temp_c=_round_int(min_values[0]),
        observed_at=current_time.isoformat(),
        timezone_name=timezone_name,
    )


def read_cached_snapshot(cache_path: Path) -> WeatherSnapshot | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        return WeatherSnapshot(**payload)
    except Exception:
        return None


def write_cached_snapshot(cache_path: Path, snapshot: WeatherSnapshot) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(asdict(snapshot), sort_keys=True) + "\n", encoding="utf-8")


def load_background(path: Path) -> Image.Image:
    if path.exists():
        return Image.open(path).convert("RGB").resize((CANVAS_WIDTH, CANVAS_HEIGHT))
    return Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), FALLBACK_BACKGROUND)


def _font(size: int, *, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _text_width(font: ImageFont.ImageFont | ImageFont.FreeTypeFont, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _fit_font(text: str, *, width_limit: int, preferred_size: int, min_size: int, bold: bool = False):
    for size in range(preferred_size, min_size - 1, -1):
        font = _font(size, bold=bold)
        if _text_width(font, text) <= width_limit:
            return font
    return _font(min_size, bold=bold)


def render_weather_frame(background: Image.Image, snapshot: WeatherSnapshot) -> Image.Image:
    frame = background.copy()
    draw = ImageDraw.Draw(frame)

    labels_font = _font(18, bold=False)
    values_font = _font(18, bold=False)
    location_font = _fit_font(snapshot.location, width_limit=120, preferred_size=18, min_size=13)

    rows = [
        ("Location:", snapshot.location, location_font),
        ("Temperature:", f"{snapshot.temperature_c}°C", values_font),
        ("Wind:", f"{snapshot.wind_kmh}km/h", values_font),
        ("Rain:", f"{snapshot.rain_probability}%", values_font),
        ("Max/Min Temp:", f"{snapshot.min_temp_c}°C/{snapshot.max_temp_c}°C", _fit_font(f"{snapshot.min_temp_c}°C/{snapshot.max_temp_c}°C", width_limit=110, preferred_size=18, min_size=12)),
    ]

    left_x = 22
    right_edge = 299
    top_y = 93
    row_gap = 32
    for index, (label, value, value_font) in enumerate(rows):
        y = top_y + index * row_gap
        draw.text((left_x, y), label, font=labels_font, fill=TEXT_COLOUR)
        value_width = _text_width(value_font, value)
        draw.text((right_edge - value_width, y), value, font=value_font, fill=TEXT_COLOUR)

    return frame


def render_unavailable_frame(background_path: Path, label: str, reason: str) -> Image.Image:
    frame = load_background(background_path)
    draw = ImageDraw.Draw(frame)
    draw.text((22, 96), "Location:", font=_font(18), fill=TEXT_COLOUR)
    draw.text((196, 96), label, font=_fit_font(label, width_limit=105, preferred_size=18, min_size=13), fill=TEXT_COLOUR)
    draw.text((22, 128), "Weather unavailable", font=_font(20, bold=True), fill=TEXT_COLOUR)
    draw.text((22, 160), reason[:28], font=_font(14), fill=TEXT_COLOUR)
    return frame


def save_frame(frame: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.save(output_path)


def run_once(config: Config, *, output_override: Path | None = None) -> int:
    tz = load_timezone(config.timezone_name)
    now = datetime.now(tz=tz)
    output_path = output_override or config.output_path
    try:
        payload = fetch_weather_payload(config)
        snapshot = parse_weather_payload(payload, location_label=config.label, fallback_time=now)
        frame = render_weather_frame(load_background(config.background_path), snapshot)
        save_frame(frame, output_path)
        write_cached_snapshot(config.cache_path, snapshot)
        print(f"[{SCRIPT_NAME}] Rendered weather image to {output_path}")
        return 0
    except (KeyError, TypeError, ValueError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        cached = read_cached_snapshot(config.cache_path)
        if cached is not None and config.output_path.exists() and output_override is None:
            print(f"[{SCRIPT_NAME}] Weather refresh failed; keeping last good image: {exc}")
            return 0
        frame = render_unavailable_frame(config.background_path, config.label, "API unavailable")
        save_frame(frame, output_path)
        print(f"[{SCRIPT_NAME}] Weather refresh failed with no cached image; rendered unavailable state: {exc}")
        return 0


def run_self_tests() -> int:
    sample_payload = {
        "timezone": "Europe/London",
        "current": {
            "time": "2026-03-13T12:00",
            "temperature_2m": 15.1,
            "wind_speed_10m": 20.4,
        },
        "hourly": {
            "time": ["2026-03-13T11:00", "2026-03-13T12:00"],
            "precipitation_probability": [10, 35],
        },
        "daily": {
            "time": ["2026-03-13"],
            "temperature_2m_max": [16.2],
            "temperature_2m_min": [7.4],
        },
    }
    snapshot = parse_weather_payload(
        sample_payload,
        location_label="Manchester",
        fallback_time=datetime(2026, 3, 13, 12, 0, tzinfo=load_timezone("Europe/London")),
    )
    if snapshot.temperature_c != 15 or snapshot.wind_kmh != 20 or snapshot.rain_probability != 35:
        raise AssertionError("weather payload should be parsed into rounded integer values")
    if snapshot.min_temp_c != 7 or snapshot.max_temp_c != 16:
        raise AssertionError("daily min/max temperatures should be rounded correctly")
    frame = render_weather_frame(Image.new("RGB", (320, 240), (0, 0, 0)), snapshot)
    if frame.size != (320, 240):
        raise AssertionError("rendered weather frame should match output dimensions")
    print("[weather_refresh.py] Self tests passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_tests()

    load_dotenv(DEFAULT_ROOT / ".env")
    config, errors = validate_config()
    if errors:
        report_validation_errors(SCRIPT_NAME, errors)
        return 1
    assert config is not None

    if args.check_config:
        print(f"[{SCRIPT_NAME}] Configuration check passed.")
        return 0

    output_override = Path(args.output).expanduser().resolve() if args.output else None
    return run_once(config, output_override=output_override)


if __name__ == "__main__":
    raise SystemExit(main())

