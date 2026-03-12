#!/usr/bin/env python3
"""Refresh a compact GTFS cache for Firswood town-centre Metrolink departures."""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import socket
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None

    class ZoneInfoNotFoundError(Exception):
        pass

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _config import get_env, report_validation_errors

DEFAULT_GTFS_URL = "https://odata.tfgm.com/opendata/downloads/TfGMgtfsnew.zip"
DEFAULT_CACHE_PATH = REPO_ROOT / "cache" / "tram_gtfs.json"
DEFAULT_TIMEOUT_SECS = 30.0
DEFAULT_STOP_ID = "123172"
DEFAULT_TIMEZONE = "Europe/London"
DEFAULT_HEADSIGNS = (
    "Victoria",
    "Rochdale Town Centre",
    "Shaw and Crompton",
)
DEFAULT_USER_AGENT = "zero2dash-trams/1.0"
METROLINK_AGENCY_ID = "7778482"
WEEKDAY_KEYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


@dataclass
class Config:
    gtfs_url: str
    cache_path: Path
    timeout_secs: float
    stop_id: str
    timezone_name: str
    target_headsigns: tuple[str, ...]
    user_agent: str


def load_timezone(name: str):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            pass
    if name in {"Europe/London", "UTC"}:
        return timezone.utc
    raise ValueError(f"Timezone data unavailable for {name!r}; install tzdata or use a host with IANA timezone support")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _as_float(name: str, value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"expected number, got {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return parsed


def _as_timezone(value: str) -> str:
    try:
        load_timezone(value)
    except Exception as exc:
        raise ValueError(f"unknown or unavailable IANA timezone {value!r}") from exc
    return value


def _parse_headsigns(value: str) -> tuple[str, ...]:
    items = tuple(part.strip() for part in value.split(",") if part.strip())
    if not items:
        raise ValueError("at least one destination is required")
    return items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh compact GTFS cache for Firswood Metrolink departures.")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and exit.")
    parser.add_argument("--force-refresh", action="store_true", help="Rewrite cache even if content is unchanged.")
    parser.add_argument("--self-test", action="store_true", help="Run inline smoke tests and exit.")
    return parser.parse_args()


def validate_config() -> tuple[Config | None, list[str]]:
    errors: list[str] = []

    def record(name: str, *, default: Any = None, required: bool = False, validator: Any = None) -> Any:
        try:
            return get_env(name, default=default, required=required, validator=validator)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    gtfs_url = str(record("TRAM_GTFS_URL", default=DEFAULT_GTFS_URL)).strip()
    cache_raw = record("TRAM_GTFS_CACHE_PATH", default=str(DEFAULT_CACHE_PATH))
    timeout_secs = float(record("TRAM_GTFS_TIMEOUT", default=DEFAULT_TIMEOUT_SECS, validator=lambda value: _as_float("TRAM_GTFS_TIMEOUT", value)))
    stop_id = str(record("TRAM_STOP_ID", default=DEFAULT_STOP_ID)).strip()
    timezone_name = str(record("TRAM_TIMEZONE", default=DEFAULT_TIMEZONE, validator=_as_timezone)).strip()
    target_headsigns = tuple(record("TRAM_TARGET_HEADSIGNS", default=",".join(DEFAULT_HEADSIGNS), validator=_parse_headsigns))
    user_agent = str(record("TRAM_GTFS_USER_AGENT", default=DEFAULT_USER_AGENT)).strip() or DEFAULT_USER_AGENT

    if not gtfs_url:
        errors.append("TRAM_GTFS_URL must not be blank")
    if not stop_id:
        errors.append("TRAM_STOP_ID must not be blank")

    if errors:
        return None, errors

    return Config(
        gtfs_url=gtfs_url,
        cache_path=expand_path(str(cache_raw)),
        timeout_secs=timeout_secs,
        stop_id=stop_id,
        timezone_name=timezone_name,
        target_headsigns=target_headsigns,
        user_agent=user_agent,
    ), []


def _load_csv_from_zip(feed_bytes: bytes, member_name: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(feed_bytes)) as archive:
        with archive.open(member_name) as handle:
            wrapper = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
            try:
                return [dict(row) for row in csv.DictReader(wrapper)]
            finally:
                wrapper.detach()


def _parse_gtfs_date(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"invalid GTFS date {value!r}")
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def _parse_departure_seconds(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid HH:MM:SS value {value!r}")
    hours, minutes, seconds = (int(part) for part in parts)
    if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60 or hours < 0:
        raise ValueError(f"invalid HH:MM:SS value {value!r}")
    return (hours * 3600) + (minutes * 60) + seconds


def download_feed(config: Config) -> bytes:
    request = urllib.request.Request(
        config.gtfs_url,
        headers={
            "User-Agent": config.user_agent,
            "Accept": "application/zip,application/octet-stream;q=0.9,*/*;q=0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=config.timeout_secs) as response:  # nosec B310
        payload = response.read()
    if not payload:
        raise ValueError("downloaded GTFS feed is empty")
    return payload


def build_cache_payload(feed_bytes: bytes, config: Config, generated_at: datetime | None = None) -> dict[str, Any]:
    generated = generated_at or datetime.now(tz=load_timezone(config.timezone_name))

    stops_rows = _load_csv_from_zip(feed_bytes, "stops.txt")
    routes_rows = _load_csv_from_zip(feed_bytes, "routes.txt")
    trips_rows = _load_csv_from_zip(feed_bytes, "trips.txt")
    stop_times_rows = _load_csv_from_zip(feed_bytes, "stop_times.txt")
    calendar_rows = _load_csv_from_zip(feed_bytes, "calendar.txt")
    calendar_dates_rows = _load_csv_from_zip(feed_bytes, "calendar_dates.txt")

    stop_lookup = {row.get("stop_id", "").strip(): row for row in stops_rows}
    target_stop = stop_lookup.get(config.stop_id)
    if not target_stop:
        raise ValueError(f"stop_id {config.stop_id} not found in GTFS feed")

    metrolink_routes = {
        row.get("route_id", "").strip()
        for row in routes_rows
        if row.get("agency_id", "").strip() == METROLINK_AGENCY_ID
    }
    if not metrolink_routes:
        raise ValueError("Metrolink agency routes were not found in GTFS feed")

    target_headsigns = set(config.target_headsigns)
    trip_lookup: dict[str, dict[str, str]] = {}
    service_ids: set[str] = set()
    for row in trips_rows:
        trip_id = row.get("trip_id", "").strip()
        service_id = row.get("service_id", "").strip()
        route_id = row.get("route_id", "").strip()
        headsign = row.get("trip_headsign", "").strip()
        if not trip_id or not service_id or not headsign:
            continue
        if route_id not in metrolink_routes or headsign not in target_headsigns:
            continue
        trip_lookup[trip_id] = {
            "service_id": service_id,
            "headsign": headsign,
            "route_id": route_id,
        }
        service_ids.add(service_id)

    if not trip_lookup:
        raise ValueError("no target Metrolink trips matched the configured headsigns")

    departures: list[dict[str, Any]] = []
    for row in stop_times_rows:
        if row.get("stop_id", "").strip() != config.stop_id:
            continue
        trip_id = row.get("trip_id", "").strip()
        trip = trip_lookup.get(trip_id)
        if trip is None:
            continue
        departure_time = row.get("departure_time", "").strip() or row.get("arrival_time", "").strip()
        if not departure_time:
            continue
        departure_secs = _parse_departure_seconds(departure_time)
        departures.append(
            {
                "trip_id": trip_id,
                "service_id": trip["service_id"],
                "headsign": trip["headsign"],
                "route_id": trip["route_id"],
                "departure_time": departure_time,
                "departure_secs": departure_secs,
            }
        )

    if not departures:
        raise ValueError("no stop_times matched the configured stop and headsigns")

    service_calendar: dict[str, dict[str, Any]] = {}
    for row in calendar_rows:
        service_id = row.get("service_id", "").strip()
        if service_id not in service_ids:
            continue
        service_calendar[service_id] = {
            "start_date": _parse_gtfs_date(row.get("start_date", "").strip()),
            "end_date": _parse_gtfs_date(row.get("end_date", "").strip()),
            "weekdays": {
                weekday: row.get(weekday, "0").strip() == "1"
                for weekday in WEEKDAY_KEYS
            },
            "added_dates": [],
            "removed_dates": [],
        }

    missing_calendar = sorted(service_ids - set(service_calendar))
    if missing_calendar:
        raise ValueError(f"calendar.txt missing service_ids used by target trips: {', '.join(missing_calendar[:5])}")

    for row in calendar_dates_rows:
        service_id = row.get("service_id", "").strip()
        calendar_entry = service_calendar.get(service_id)
        if calendar_entry is None:
            continue
        exception_date = _parse_gtfs_date(row.get("date", "").strip())
        exception_type = row.get("exception_type", "").strip()
        if exception_type == "1":
            calendar_entry["added_dates"].append(exception_date)
        elif exception_type == "2":
            calendar_entry["removed_dates"].append(exception_date)

    for calendar_entry in service_calendar.values():
        calendar_entry["added_dates"].sort()
        calendar_entry["removed_dates"].sort()

    departures.sort(key=lambda item: (item["departure_secs"], item["headsign"], item["trip_id"]))

    stop_name = target_stop.get("stop_name", "").strip() or f"Stop {config.stop_id}"
    stop_code = target_stop.get("stop_code", "").strip()

    return {
        "generated_at": generated.isoformat(),
        "source_url": config.gtfs_url,
        "timezone": config.timezone_name,
        "agency_id": METROLINK_AGENCY_ID,
        "stop_id": config.stop_id,
        "stop_code": stop_code,
        "stop_name": stop_name,
        "target_headsigns": list(config.target_headsigns),
        "departures": departures,
        "service_calendar": service_calendar,
    }


def save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_once(*, force_refresh: bool = False) -> int:
    configure_logging()

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    config, errors = validate_config()
    if errors:
        report_validation_errors("tram_gtfs_refresh.py", errors)
        return 1
    assert config is not None

    try:
        feed_bytes = download_feed(config)
        payload = build_cache_payload(feed_bytes, config)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, zipfile.BadZipFile, ValueError) as exc:
        logging.error("Unable to refresh tram GTFS cache: %s", exc)
        return 1

    if not force_refresh and config.cache_path.exists():
        existing = config.cache_path.read_text(encoding="utf-8")
        candidate = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if existing == candidate:
            logging.info("Tram GTFS cache already current; no refresh required.")
            return 0

    save_cache(config.cache_path, payload)
    logging.info("Wrote tram GTFS cache: %s", config.cache_path)
    return 0


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _build_test_feed() -> bytes:
    files = {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\n7778482,Metrolink,https://example.com,Europe/London\n",
        "routes.txt": "route_id,agency_id,route_short_name,route_long_name,route_type\nM1,7778482,,Metrolink,0\nB1,999,,Bus,3\n",
        "stops.txt": "stop_id,stop_code,stop_name\n123172,9400ZZMAFIR1,Firswood (Manchester Metrolink)\n123173,9400ZZMAFIR2,Firswood (Manchester Metrolink)\n",
        "trips.txt": "route_id,service_id,trip_id,trip_headsign,direction_id\nM1,WEEKDAY,T1,Victoria,1\nM1,WEEKDAY,T2,Rochdale Town Centre,1\nM1,WEEKEND,T3,Shaw and Crompton,1\nM1,WEEKDAY,T4,Exchange Square,1\nB1,WEEKDAY,T5,Victoria,1\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nT1,08:11:00,08:12:00,123172,10\nT2,25:03:00,25:03:00,123172,20\nT3,09:00:00,09:01:00,123172,30\nT4,10:00:00,10:00:00,123172,40\nT5,11:00:00,11:00:00,123172,50\nT1,08:10:00,08:10:00,123173,10\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nWEEKDAY,1,1,1,1,1,0,0,20260301,20260331\nWEEKEND,0,0,0,0,0,1,1,20260301,20260331\n",
        "calendar_dates.txt": "service_id,date,exception_type\nWEEKDAY,20260317,2\nWEEKEND,20260317,1\n",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def run_self_tests() -> int:
    configure_logging()
    config = Config(
        gtfs_url="https://example.invalid/feed.zip",
        cache_path=Path(tempfile.gettempdir()) / "tram-gtfs-self-test.json",
        timeout_secs=5.0,
        stop_id=DEFAULT_STOP_ID,
        timezone_name=DEFAULT_TIMEZONE,
        target_headsigns=DEFAULT_HEADSIGNS,
        user_agent=DEFAULT_USER_AGENT,
    )
    payload = build_cache_payload(_build_test_feed(), config, generated_at=datetime(2026, 3, 12, 9, 30, tzinfo=load_timezone(DEFAULT_TIMEZONE)))
    _assert(payload["stop_name"] == "Firswood (Manchester Metrolink)", "expected target stop name")
    _assert(payload["target_headsigns"] == list(DEFAULT_HEADSIGNS), "expected configured headsigns")
    _assert([item["headsign"] for item in payload["departures"]] == ["Victoria", "Shaw and Crompton", "Rochdale Town Centre"], "unexpected departure filtering")
    weekday_service = payload["service_calendar"]["WEEKDAY"]
    _assert("2026-03-17" in weekday_service["removed_dates"], "weekday exception removal missing")
    weekend_service = payload["service_calendar"]["WEEKEND"]
    _assert("2026-03-17" in weekend_service["added_dates"], "weekend exception addition missing")
    print("[tram_gtfs_refresh.py] Self tests passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_tests()

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    config, errors = validate_config()
    if errors:
        report_validation_errors("tram_gtfs_refresh.py", errors)
        return 1
    if args.check_config:
        print("[tram_gtfs_refresh.py] Configuration check passed.")
        return 0

    return run_once(force_refresh=args.force_refresh)


if __name__ == "__main__":
    raise SystemExit(main())
