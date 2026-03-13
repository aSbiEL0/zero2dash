from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime
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


weather_refresh = _load_module("weather_refresh", "modules/weather/weather_refresh.py")


class WeatherTests(unittest.TestCase):
    def test_parse_weather_payload_rounds_values_and_uses_current_hour_rain(self) -> None:
        payload = {
            "timezone": "Europe/London",
            "current": {
                "time": "2026-03-13T12:00",
                "temperature_2m": 15.4,
                "wind_speed_10m": 19.6,
            },
            "hourly": {
                "time": ["2026-03-13T11:00", "2026-03-13T12:00"],
                "precipitation_probability": [12, 35],
            },
            "daily": {
                "time": ["2026-03-13"],
                "temperature_2m_max": [16.2],
                "temperature_2m_min": [7.4],
            },
        }
        snapshot = weather_refresh.parse_weather_payload(
            payload,
            location_label="Manchester",
            fallback_time=datetime(2026, 3, 13, 12, 0, tzinfo=weather_refresh.load_timezone("Europe/London")),
        )
        self.assertEqual(snapshot.temperature_c, 15)
        self.assertEqual(snapshot.wind_kmh, 20)
        self.assertEqual(snapshot.rain_probability, 35)
        self.assertEqual(snapshot.max_temp_c, 16)
        self.assertEqual(snapshot.min_temp_c, 7)

    def test_select_hourly_value_returns_zero_when_time_missing(self) -> None:
        selected = weather_refresh.select_hourly_value(
            ["2026-03-13T10:00"],
            [85],
            datetime(2026, 3, 13, 12, 12),
        )
        self.assertEqual(selected, 0)

    def test_run_once_keeps_existing_image_when_fetch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "weather.png"
            output_path.write_bytes(b"existing")
            cache_path = temp_path / "weather-cache.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "location": "Manchester",
                        "temperature_c": 15,
                        "wind_kmh": 20,
                        "rain_probability": 35,
                        "max_temp_c": 16,
                        "min_temp_c": 7,
                        "observed_at": "2026-03-13T12:00:00+00:00",
                        "timezone_name": "Europe/London",
                    }
                ),
                encoding="utf-8",
            )
            config = weather_refresh.Config(
                lat=53.4808,
                lon=-2.2426,
                label="Manchester",
                timezone_name="Europe/London",
                timeout_secs=5.0,
                api_base="https://example.invalid",
                output_path=output_path,
                cache_path=cache_path,
                background_path=REPO_ROOT / "modules" / "weather" / "weather-background.png",
            )
            original_fetch = weather_refresh.fetch_weather_payload
            try:
                def _boom(_config):
                    raise ValueError("boom")
                weather_refresh.fetch_weather_payload = _boom
                rc = weather_refresh.run_once(config)
            finally:
                weather_refresh.fetch_weather_payload = original_fetch
            self.assertEqual(rc, 0)
            self.assertEqual(output_path.read_bytes(), b"existing")

    def test_render_weather_frame_smoke_test(self) -> None:
        background = weather_refresh.load_background(REPO_ROOT / "modules" / "weather" / "weather-background.png")
        snapshot = weather_refresh.WeatherSnapshot(
            location="Manchester",
            temperature_c=15,
            wind_kmh=20,
            rain_probability=35,
            max_temp_c=16,
            min_temp_c=7,
            observed_at="2026-03-13T12:00:00+00:00",
            timezone_name="Europe/London",
        )
        frame = weather_refresh.render_weather_frame(background, snapshot)
        self.assertEqual(frame.size, (320, 240))


if __name__ == "__main__":
    unittest.main()
