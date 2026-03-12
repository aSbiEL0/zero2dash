from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tram_gtfs_refresh = _load_module("tram_gtfs_refresh", "modules/trams/tram_gtfs_refresh.py")
tram_display = _load_module("tram_display", "modules/trams/display.py")


class TramTests(unittest.TestCase):
    def test_build_cache_payload_filters_target_trips(self) -> None:
        config = tram_gtfs_refresh.Config(
            gtfs_url="https://example.invalid/feed.zip",
            cache_path=REPO_ROOT / "cache" / "tram_gtfs_test.json",
            timeout_secs=5.0,
            stop_id="123172",
            timezone_name="Europe/London",
            target_headsigns=("Victoria", "Rochdale Town Centre", "Shaw and Crompton"),
            user_agent="zero2dash-test",
        )
        payload = tram_gtfs_refresh.build_cache_payload(
            tram_gtfs_refresh._build_test_feed(),
            config,
            generated_at=datetime(2026, 3, 12, 9, 30, tzinfo=tram_gtfs_refresh.load_timezone("Europe/London")),
        )
        self.assertEqual(payload["stop_code"], "9400ZZMAFIR1")
        self.assertEqual(
            [item["headsign"] for item in payload["departures"]],
            ["Victoria", "Shaw and Crompton", "Rochdale Town Centre"],
        )
        self.assertIn("2026-03-17", payload["service_calendar"]["WEEKEND"]["added_dates"])

    def test_compute_upcoming_departures_includes_previous_service_day_after_midnight(self) -> None:
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
                {"service_id": "WK", "headsign": "Victoria", "departure_time": "23:55:00", "departure_secs": 23 * 3600 + 55 * 60},
                {"service_id": "WK", "headsign": "Rochdale Town Centre", "departure_time": "25:03:00", "departure_secs": 25 * 3600 + 3 * 60},
            ],
        }
        now = datetime(2026, 3, 17, 0, 30, tzinfo=tram_display.load_timezone("Europe/London"))
        upcoming = tram_display.compute_upcoming_departures(cache, now, limit=3)
        self.assertGreaterEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0].headsign, "Rochdale Town Centre")
        self.assertEqual(upcoming[0].departure_dt.hour, 1)
        self.assertEqual(upcoming[0].minutes, 33)

    def test_service_runs_on_obeys_overrides(self) -> None:
        service = {
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "weekdays": {
                "monday": False,
                "tuesday": False,
                "wednesday": False,
                "thursday": False,
                "friday": False,
                "saturday": False,
                "sunday": False,
            },
            "added_dates": ["2026-03-17"],
            "removed_dates": ["2026-03-18"],
        }
        self.assertTrue(tram_display.service_runs_on(service, date(2026, 3, 17)))
        self.assertFalse(tram_display.service_runs_on(service, date(2026, 3, 18)))


if __name__ == "__main__":
    unittest.main()
