#!/usr/bin/env python3
"""Refresh compact GTFS timetable cache for the Firswood tram module."""

from __future__ import annotations

import argparse
import csv
import email.utils
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
from typing import Any, Iterator

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
DEFAULT_CACHE_PATH = MODULE_DIR / "tram_timetable.json"
DEFAULT_TIMEOUT_SECS = 30.0
DEFAULT_STOP_NAME = "Firswood"
DEFAULT_STOP_ID = ""
DEFAULT_TIMEZONE = "Europe/London"
DEFAULT_DIRECTION_LABEL = "towards Town Centre"
DEFAULT_HEADSIGNS = (
    "Victoria",
    "Shaw and Crompton",
    "Rochdale Town Centre",
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
    stop_name: str
    stop_id: str
    timezone_name: str
    direction_label: str
    target_headsigns: tuple[str, ...]
    user_agent: str


@dataclass
class DownloadResult:
    payload: bytes
    last_modified: str | None


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
    parser = argparse.ArgumentParser(description="Refresh compact GTFS timetable cache for Firswood tram departures.")
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
    stop_name = str(record("TRAM_STOP_NAME", default=DEFAULT_STOP_NAME)).strip()
    stop_id = str(record("TRAM_STOP_ID", default=DEFAULT_STOP_ID)).strip()
    timezone_name = str(record("TRAM_TIMEZONE", default=DEFAULT_TIMEZONE, validator=_as_timezone)).strip()
    direction_label = str(record("TRAM_DIRECTION_LABEL", default=DEFAULT_DIRECTION_LABEL)).strip()
    target_headsigns = tuple(record("TRAM_TARGET_HEADSIGNS", default=",".join(DEFAULT_HEADSIGNS), validator=_parse_headsigns))
    user_agent = str(record("TRAM_GTFS_USER_AGENT", default=DEFAULT_USER_AGENT)).strip() or DEFAULT_USER_AGENT

    if not gtfs_url:
        errors.append("TRAM_GTFS_URL must not be blank")
    if not stop_name and not stop_id:
        errors.append("TRAM_STOP_NAME or TRAM_STOP_ID must be set")
    if not direction_label:
        errors.append("TRAM_DIRECTION_LABEL must not be blank")

    if errors:
        return None, errors

    return Config(
        gtfs_url=gtfs_url,
        cache_path=expand_path(str(cache_raw)),
        timeout_secs=timeout_secs,
        stop_name=stop_name,
        stop_id=stop_id,
        timezone_name=timezone_name,
        direction_label=direction_label,
        target_headsigns=target_headsigns,
        user_agent=user_agent,
    ), []


def _iter_csv_rows(archive: zipfile.ZipFile, member_name: str) -> Iterator[dict[str, str]]:
    with archive.open(member_name) as handle:
        wrapper = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
        try:
            for row in csv.DictReader(wrapper):
                yield dict(row)
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


def download_feed(config: Config) -> DownloadResult:
    request = urllib.request.Request(
        config.gtfs_url,
        headers={
            "User-Agent": config.user_agent,
            "Accept": "application/zip,application/octet-stream;q=0.9,*/*;q=0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=config.timeout_secs) as response:  # nosec B310
        payload = response.read()
        last_modified_raw = response.headers.get("Last-Modified", "").strip()
    if not payload:
        raise ValueError("downloaded GTFS feed is empty")
    last_modified: str | None = None
    if last_modified_raw:
        try:
            parsed = email.utils.parsedate_to_datetime(last_modified_raw)
            last_modified = parsed.astimezone(timezone.utc).isoformat()
        except Exception:
            last_modified = last_modified_raw
    return DownloadResult(payload=payload, last_modified=last_modified)


def _normalise_stop_name(value: str) -> str:
    lowered = value.lower().replace("(manchester metrolink)", "")
    return " ".join(lowered.split())


def _load_candidate_stops(archive: zipfile.ZipFile, config: Config) -> list[dict[str, str]]:
    if config.stop_id:
        for row in _iter_csv_rows(archive, "stops.txt"):
            if row.get("stop_id", "").strip() == config.stop_id:
                return [row]
        raise ValueError(f"stop_id {config.stop_id} not found in GTFS feed")

    target_name = _normalise_stop_name(config.stop_name)
    candidate_stops = [
        row
        for row in _iter_csv_rows(archive, "stops.txt")
        if target_name and target_name in _normalise_stop_name(row.get("stop_name", "").strip())
    ]
    if not candidate_stops:
        raise ValueError(f"no stop records matched stop name {config.stop_name!r}")
    return candidate_stops


def _collect_stop_evidence_and_departures(
    archive: zipfile.ZipFile,
    candidate_stops: list[dict[str, str]],
    trip_lookup: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    candidate_stop_ids = {row.get("stop_id", "").strip() for row in candidate_stops if row.get("stop_id", "").strip()}
    if not candidate_stop_ids:
        raise ValueError("candidate stop set was empty")

    matches_by_stop: dict[str, int] = {stop_id: 0 for stop_id in candidate_stop_ids}
    departures_by_stop: dict[str, list[dict[str, Any]]] = {stop_id: [] for stop_id in candidate_stop_ids}
    for row in _iter_csv_rows(archive, "stop_times.txt"):
        stop_id = row.get("stop_id", "").strip()
        if stop_id not in matches_by_stop:
            continue
        trip_id = row.get("trip_id", "").strip()
        trip = trip_lookup.get(trip_id)
        if trip is None:
            continue

        matches_by_stop[stop_id] += 1
        departure_time = row.get("departure_time", "").strip() or row.get("arrival_time", "").strip()
        if not departure_time:
            continue
        departures_by_stop[stop_id].append(
            {
                "trip_id": trip_id,
                "service_id": trip["service_id"],
                "headsign": trip["headsign"],
                "route_id": trip["route_id"],
                "departure_time": departure_time,
                "departure_secs": _parse_departure_seconds(departure_time),
            }
        )

    evidence = [
        {
            "stop_id": row.get("stop_id", "").strip(),
            "stop_code": row.get("stop_code", "").strip(),
            "stop_name": row.get("stop_name", "").strip(),
            "matching_departures": matches_by_stop.get(row.get("stop_id", "").strip(), 0),
        }
        for row in candidate_stops
    ]
    evidence.sort(key=lambda item: (-int(item["matching_departures"]), item["stop_code"], item["stop_id"]))
    return evidence, departures_by_stop


def _resolve_target_stop(
    candidate_stops: list[dict[str, str]],
    evidence: list[dict[str, Any]],
    config: Config,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    best = evidence[0]
    if int(best["matching_departures"]) <= 0:
        if config.stop_id:
            raise ValueError(f"stop_id {config.stop_id} had no matching departures for the target headsigns")
        raise ValueError(f"no candidate stop for {config.stop_name!r} had matching departures for the target headsigns")
    target = next(row for row in candidate_stops if row.get("stop_id", "").strip() == best["stop_id"])
    return target, evidence


def build_cache_payload(
    feed_bytes: bytes,
    config: Config,
    *,
    source_last_modified: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(tz=load_timezone(config.timezone_name))

    with zipfile.ZipFile(io.BytesIO(feed_bytes)) as archive:
        metrolink_routes = {
            row.get("route_id", "").strip()
            for row in _iter_csv_rows(archive, "routes.txt")
            if row.get("agency_id", "").strip() == METROLINK_AGENCY_ID
        }
        if not metrolink_routes:
            raise ValueError("Metrolink agency routes were not found in GTFS feed")

        target_headsigns = set(config.target_headsigns)
        trip_lookup: dict[str, dict[str, str]] = {}
        service_ids: set[str] = set()
        for row in _iter_csv_rows(archive, "trips.txt"):
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

        candidate_stops = _load_candidate_stops(archive, config)
        stop_evidence, departures_by_stop = _collect_stop_evidence_and_departures(archive, candidate_stops, trip_lookup)
        target_stop, stop_evidence = _resolve_target_stop(candidate_stops, stop_evidence, config)
        target_stop_id = target_stop.get("stop_id", "").strip()
        if not target_stop_id:
            raise ValueError("resolved stop record did not contain stop_id")

        departures = departures_by_stop.get(target_stop_id, [])
        if not departures:
            raise ValueError("no stop_times matched the resolved stop and target headsigns")

        service_calendar: dict[str, dict[str, Any]] = {}
        for row in _iter_csv_rows(archive, "calendar.txt"):
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

        for row in _iter_csv_rows(archive, "calendar_dates.txt"):
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
    stop_name = target_stop.get("stop_name", "").strip() or config.stop_name or f"Stop {target_stop_id}"

    return {
        "generated_at": generated.isoformat(),
        "source_url": config.gtfs_url,
        "source_last_modified": source_last_modified,
        "timezone": config.timezone_name,
        "direction_label": config.direction_label,
        "agency_id": METROLINK_AGENCY_ID,
        "stop": {
            "stop_id": target_stop_id,
            "stop_code": target_stop.get("stop_code", "").strip(),
            "stop_name": stop_name,
            "requested_stop_name": config.stop_name,
            "requested_stop_id": config.stop_id,
            "resolution_evidence": stop_evidence,
        },
        "target_headsigns": list(config.target_headsigns),
        "departures": departures,
        "service_calendar": service_calendar,
    }


def load_repo_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env")


def save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def run_once(*, force_refresh: bool = False, config_override: Config | None = None) -> int:
    configure_logging()

    load_repo_env()
    config = config_override
    if config is None:
        config, errors = validate_config()
        if errors:
            report_validation_errors("tram_gtfs_refresh.py", errors)
            return 1
    assert config is not None

    try:
        download = download_feed(config)
        payload = build_cache_payload(download.payload, config, source_last_modified=download.last_modified)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, zipfile.BadZipFile, ValueError) as exc:
        logging.error("Unable to refresh tram timetable cache: %s", exc)
        return 1

    candidate = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if not force_refresh and config.cache_path.exists():
        existing = config.cache_path.read_text(encoding="utf-8")
        if existing == candidate:
            logging.info("Tram timetable cache already current; no refresh required.")
            return 0

    save_cache(config.cache_path, payload)
    logging.info("Wrote tram timetable cache: %s", config.cache_path)
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
        cache_path=Path(tempfile.gettempdir()) / "tram-timetable-self-test.json",
        timeout_secs=5.0,
        stop_name="Firswood",
        stop_id="",
        timezone_name=DEFAULT_TIMEZONE,
        direction_label=DEFAULT_DIRECTION_LABEL,
        target_headsigns=DEFAULT_HEADSIGNS,
        user_agent=DEFAULT_USER_AGENT,
    )
    payload = build_cache_payload(
        _build_test_feed(),
        config,
        source_last_modified="2026-03-12T09:20:00+00:00",
        generated_at=datetime(2026, 3, 12, 9, 30, tzinfo=load_timezone(DEFAULT_TIMEZONE)),
    )
    _assert(payload["stop"]["stop_code"] == "9400ZZMAFIR1", "expected FIR1 platform resolution")
    _assert(payload["direction_label"] == DEFAULT_DIRECTION_LABEL, "expected direction label")
    _assert([item["headsign"] for item in payload["departures"]] == ["Victoria", "Shaw and Crompton", "Rochdale Town Centre"], "unexpected departure filtering")
    print("[tram_gtfs_refresh.py] Self tests passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_tests()

    load_repo_env()
    config, errors = validate_config()
    if errors:
        report_validation_errors("tram_gtfs_refresh.py", errors)
        return 1
    if args.check_config:
        print("[tram_gtfs_refresh.py] Configuration check passed.")
        return 0

    return run_once(force_refresh=args.force_refresh, config_override=config)


if __name__ == "__main__":
    raise SystemExit(main())
