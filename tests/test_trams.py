from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
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
tram_alerts_refresh = _load_module("tram_alerts_refresh", "modules/trams/tram_alerts_refresh.py")


class TramTests(unittest.TestCase):
    def test_build_cache_payload_resolves_firswood_platform_and_filters_target_trips(self) -> None:
        config = tram_gtfs_refresh.Config(
            gtfs_url="https://example.invalid/feed.zip",
            cache_path=REPO_ROOT / "modules" / "trams" / "tram_timetable_test.json",
            timeout_secs=5.0,
            stop_name="Firswood",
            stop_id="",
            timezone_name="Europe/London",
            direction_label="towards Town Centre",
            target_headsigns=("Victoria", "Rochdale Town Centre", "Shaw and Crompton"),
            user_agent="zero2dash-test",
        )
        payload = tram_gtfs_refresh.build_cache_payload(
            tram_gtfs_refresh._build_test_feed(),
            config,
            source_last_modified="2026-03-12T09:20:00+00:00",
            generated_at=datetime(2026, 3, 12, 9, 30, tzinfo=tram_gtfs_refresh.load_timezone("Europe/London")),
        )
        self.assertEqual(payload["stop"]["stop_code"], "9400ZZMAFIR1")
        self.assertEqual([item["headsign"] for item in payload["departures"]], ["Victoria", "Shaw and Crompton", "Rochdale Town Centre"])
        self.assertIn("2026-03-17", payload["service_calendar"]["WEEKEND"]["added_dates"])

    def test_compute_upcoming_departures_uses_today_only(self) -> None:
        cache = {
            "timezone": "Europe/London",
            "service_calendar": {
                "WK": {
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-31",
                    "weekdays": {
                        "monday": False,
                        "tuesday": True,
                        "wednesday": False,
                        "thursday": False,
                        "friday": False,
                        "saturday": False,
                        "sunday": False,
                    },
                    "added_dates": [],
                    "removed_dates": [],
                }
            },
            "departures": [
                {"service_id": "WK", "headsign": "Victoria", "departure_time": "00:40:00", "departure_secs": 40 * 60},
                {"service_id": "WK", "headsign": "Rochdale Town Centre", "departure_time": "25:03:00", "departure_secs": 25 * 3600 + 3 * 60},
            ],
        }
        now = datetime(2026, 3, 17, 0, 30, tzinfo=tram_display.load_timezone("Europe/London"))
        upcoming = tram_display.compute_upcoming_departures(cache, now, limit=4)
        self.assertEqual([item.headsign for item in upcoming], ["Victoria", "Rochdale Town Centre"])
        self.assertEqual(upcoming[0].minutes, 10)

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

    def test_ticker_fallback_states(self) -> None:
        self.assertEqual(tram_display.ticker_text_from_alerts(None), "Alerts unavailable")
        self.assertEqual(tram_display.ticker_text_from_alerts({"items": []}), "No current tram alerts")

    def test_ticker_rotates_between_alerts(self) -> None:
        alerts = {"items": [{"ticker_text": "Alert A"}, {"ticker_text": "Alert B"}, {"ticker_text": "Alert C"}]}
        self.assertEqual(tram_display.ticker_text_from_alerts(alerts, now=datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)), "Alert A")
        self.assertEqual(tram_display.ticker_text_from_alerts(alerts, now=datetime(1970, 1, 1, 0, 0, 15, tzinfo=timezone.utc)), "Alert B")
        self.assertEqual(tram_display.ticker_text_from_alerts(alerts, now=datetime(1970, 1, 1, 0, 0, 30, tzinfo=timezone.utc)), "Alert C")

    def test_alert_parser_and_filter_keep_route_relevant_items(self) -> None:
        structured = json.dumps({"items": [{"title": "Tram disruption at Cornbrook", "description": "Services between Firswood and Trafford Centre are delayed."}, {"title": "Bus diversion", "description": "Not relevant."}]})
        alerts = tram_alerts_refresh.parse_structured_alerts(structured, "https://example.invalid")
        filtered = tram_alerts_refresh.filter_alerts(alerts)
        self.assertEqual([item.title for item in filtered], ["Tram disruption at Cornbrook"])

    def test_alert_refresh_preserves_existing_cache_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "tram_alerts.json"
            cache_path.write_text(json.dumps({"items": [{"ticker_text": "existing"}]}), encoding="utf-8")
            config = tram_alerts_refresh.Config(alerts_url="https://example.invalid/alerts", cache_path=cache_path, timeout_secs=1.0, user_agent="zero2dash-test")
            original_download = tram_alerts_refresh.download_alert_source
            try:
                def _boom(_config):
                    raise ValueError("boom")
                tram_alerts_refresh.download_alert_source = _boom
                rc = tram_alerts_refresh.run_once(force_refresh=False, config_override=config)
            finally:
                tram_alerts_refresh.download_alert_source = original_download
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(cache_path.read_text(encoding="utf-8"))["items"][0]["ticker_text"], "existing")

    def test_render_frame_smoke_test_with_background_asset(self) -> None:
        background = tram_display.load_background(REPO_ROOT / "modules" / "trams" / "tram-background.png", 320, 240)
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
                        "saturday": True,
                        "sunday": True,
                    },
                    "added_dates": [],
                    "removed_dates": [],
                }
            },
            "departures": [{"service_id": "WK", "headsign": "Victoria", "departure_time": "08:12:00", "departure_secs": 8 * 3600 + 12 * 60}],
        }
        frame = tram_display.render_frame(background, cache, {"items": [{"ticker_text": "Service change at Cornbrook"}]}, datetime(2026, 3, 16, 8, 0, tzinfo=tram_display.load_timezone("Europe/London")), ticker_offset=8)
        self.assertEqual(frame.size, (320, 240))


if __name__ == "__main__":
    unittest.main()

