import importlib.util
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile

MODULE_PATH = Path(__file__).resolve().parent.parent / "app.py"
SPEC = importlib.util.spec_from_file_location("nasa_app_module", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
NASA_APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = NASA_APP
SPEC.loader.exec_module(NASA_APP)


class NasaAppTests(unittest.TestCase):
    def build_location(
        self,
        *,
        country_code: str = "GB",
        country_name: str = "United Kingdom",
        location_label: str = "United Kingdom",
    ) -> object:
        return NASA_APP.LocationSnapshot(
            source="test",
            fetched_at=1,
            position_timestamp=2,
            latitude=51.5,
            longitude=-0.12,
            altitude_km=408.4,
            velocity_kmh=27600.0,
            country_code=country_code,
            country_name=country_name,
            location_label=location_label,
            visibility="Daylight",
            trail=[],
            details_timestamp=2,
        )

    def build_crew_snapshot(self, count: int = 4) -> object:
        return NASA_APP.CrewSnapshot(
            source="test",
            fetched_at=1,
            crew=[
                NASA_APP.CrewMember(
                    f"Crew {index}",
                    "Astronaut",
                    "ISS",
                    "NASA",
                    None,
                    None,
                    None,
                    "Astronaut | ISS",
                )
                for index in range(count)
            ],
            expedition="Expedition 72",
            expedition_reason="Expedition 72 | Commander",
        )

    def test_deserialize_location_supports_legacy_flyover_field(self) -> None:
        payload = {
            "source": "cache",
            "fetched_at": 1,
            "position_timestamp": 2,
            "latitude": 10.0,
            "longitude": 20.0,
            "altitude_km": 408.0,
            "velocity_kmh": 27600.0,
            "country_code": "GB",
            "country_name": "United Kingdom",
            "location_label": "United Kingdom",
            "flyover_status": "eclipsed",
            "trail": [],
            "details_timestamp": 3,
        }
        snapshot = NASA_APP.deserialize_location(payload)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.visibility, "eclipsed")

    def test_deserialize_location_sanitizes_placeholder_location_fields(self) -> None:
        payload = {
            "source": "cache",
            "fetched_at": 1,
            "position_timestamp": 2,
            "latitude": 10.0,
            "longitude": 20.0,
            "altitude_km": 408.0,
            "velocity_kmh": 27600.0,
            "country_code": "??",
            "country_name": "unknown",
            "location_label": "??",
            "visibility": "eclipsed",
            "trail": [],
            "details_timestamp": 3,
        }
        snapshot = NASA_APP.deserialize_location(payload)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.country_code, "")
        self.assertEqual(snapshot.country_name, "")
        self.assertEqual(snapshot.location_label, "")

    def test_parse_corquaid_crew_builds_expedition_reason(self) -> None:
        payload = {
            "expedition": "72",
            "people": [
                {
                    "name": "Alice Example",
                    "craft": "ISS",
                    "position": "Commander",
                    "agency": "NASA",
                    "spacecraft": "ISS",
                    "days_in_space": 100,
                }
            ],
        }
        crew, expedition, reason = NASA_APP.parse_corquaid_crew(payload)
        self.assertEqual(len(crew), 1)
        self.assertEqual(expedition, "Expedition 72")
        self.assertEqual(reason, "Expedition 72 | Commander")

    def test_map_asset_constants_point_to_map_art(self) -> None:
        self.assertEqual(NASA_APP.MAP_TEMPLATE_PATH.name, "map.png")
        self.assertEqual(NASA_APP.MAP_STALE_TEMPLATE_PATH.name, "map-error.png")

    def test_map_overlay_constants_match_new_map_guide(self) -> None:
        self.assertEqual(
            (
                NASA_APP.MAP_OVERLAY_X,
                NASA_APP.MAP_OVERLAY_Y,
                NASA_APP.MAP_OVERLAY_WIDTH,
                NASA_APP.MAP_OVERLAY_HEIGHT,
            ),
            (0, 40, 320, 160),
        )

    def test_text_box_constants_match_new_guide(self) -> None:
        self.assertEqual(
            (
                NASA_APP.DETAILS_CONTENT_X,
                NASA_APP.DETAILS_CONTENT_Y,
                NASA_APP.DETAILS_CONTENT_WIDTH,
                NASA_APP.DETAILS_CONTENT_HEIGHT,
                NASA_APP.DETAILS_LABEL_X,
                NASA_APP.DETAILS_LABEL_WIDTH,
                NASA_APP.DETAILS_VALUE_X,
                NASA_APP.DETAILS_VALUE_WIDTH,
                NASA_APP.CREW_CONTENT_X,
                NASA_APP.CREW_CONTENT_WIDTH,
            ),
            (30, 30, 260, 180, 30, 120, 170, 120, 30, 260),
        )

    def test_map_point_matches_new_full_width_band(self) -> None:
        map_box = NASA_APP.overlay_bounds(
            NASA_APP.MAP_OVERLAY_X,
            NASA_APP.MAP_OVERLAY_Y,
            NASA_APP.MAP_OVERLAY_WIDTH,
            NASA_APP.MAP_OVERLAY_HEIGHT,
        )
        self.assertEqual(NASA_APP.map_point(0.0, 0.0, map_box), (160, 120))
        self.assertEqual(NASA_APP.map_point(0.0, -180.0, map_box), (0, 120))
        self.assertEqual(NASA_APP.map_point(0.0, 180.0, map_box), (320, 120))
        self.assertEqual(NASA_APP.map_point(90.0, 0.0, map_box), (160, 40))
        self.assertEqual(NASA_APP.map_point(-90.0, 0.0, map_box), (160, 200))

    def test_render_map_page_uses_map_asset_candidates(self) -> None:
        with patch.object(
            NASA_APP,
            "load_asset_candidates",
            return_value=NASA_APP.Image.new("RGB", (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT)),
        ) as load_asset_candidates:
            image = NASA_APP.render_map_page(self.build_location(), stale=True)
        self.assertEqual(image.size, (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))
        load_asset_candidates.assert_called_once_with(
            NASA_APP.MAP_STALE_TEMPLATE_PATH,
            NASA_APP.MAP_TEMPLATE_PATH,
            NASA_APP.ERROR_TEMPLATE_PATH,
        )

    def test_location_display_name_prefers_country_name_then_location_label(self) -> None:
        self.assertEqual(
            NASA_APP.location_display_name(self.build_location(country_name="United Kingdom", location_label="North Sea")),
            "United Kingdom",
        )
        self.assertEqual(
            NASA_APP.location_display_name(self.build_location(country_name="", location_label="North Sea")),
            "North Sea",
        )
        international_waters = self.build_location(country_code="", country_name="", location_label="")
        self.assertEqual(NASA_APP.location_display_name(international_waters), "Unknown")

    def test_location_display_name_ignores_placeholder_values(self) -> None:
        placeholder_location = self.build_location(country_code="??", country_name="??", location_label="??")
        self.assertEqual(NASA_APP.location_display_name(placeholder_location), "Unknown")

    def test_build_details_entries_match_requested_rows(self) -> None:
        entries = NASA_APP.build_details_entries(self.build_location())
        self.assertEqual(
            [label for label, _value in entries],
            ["Longitude:", "Latitude:", "Currently over:", "Altitude:", "Velocity:", "Day/Night:"],
        )

    def test_geoapify_api_key_accepts_raw_key(self) -> None:
        with patch.dict(NASA_APP.os.environ, {NASA_APP.GEOAPIFY_API_KEY_ENV: "raw-test-key"}, clear=False):
            self.assertEqual(NASA_APP.geoapify_api_key(), "raw-test-key")

    def test_geoapify_api_key_extracts_key_from_full_url(self) -> None:
        full_url = "https://api.geoapify.com/v1/geocode/reverse?lat=51.5&lon=-0.12&apiKey=test-key-123"
        with patch.dict(NASA_APP.os.environ, {NASA_APP.GEOAPIFY_API_KEY_ENV: full_url}, clear=False):
            self.assertEqual(NASA_APP.geoapify_api_key(), "test-key-123")

    def test_format_velocity_returns_plain_speed_text(self) -> None:
        self.assertEqual(NASA_APP.format_velocity(self.build_location()), "27,600 km/h")

    def test_normalise_day_night_maps_visibility_to_simple_labels(self) -> None:
        self.assertEqual(NASA_APP.normalise_day_night("Daylight"), "Day")
        self.assertEqual(NASA_APP.normalise_day_night("eclipsed"), "Night")
        self.assertEqual(NASA_APP.normalise_day_night(""), "Unknown")

    def test_details_page_renders_with_location_display_name_fallback(self) -> None:
        location = self.build_location(country_name="", location_label="North Sea")
        with patch.object(NASA_APP, "location_display_name", return_value="North Sea") as location_display_name:
            image = NASA_APP.render_details_page(location, stale=True)
        self.assertEqual(image.size, (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))
        location_display_name.assert_called_once_with(location)

    def test_render_loading_page_uses_loading_asset_candidates(self) -> None:
        with patch.object(
            NASA_APP,
            "load_asset_candidates",
            return_value=NASA_APP.Image.new("RGB", (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT)),
        ) as load_asset_candidates:
            image = NASA_APP.render_loading_page("crew")
        self.assertEqual(image.size, (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))
        load_asset_candidates.assert_called_once_with(
            NASA_APP.LOADING_TEMPLATE_PATH,
            NASA_APP.MAP_TEMPLATE_PATH,
            NASA_APP.DETAILS_TEMPLATE_PATH,
            NASA_APP.ERROR_TEMPLATE_PATH,
        )

    def test_fetch_trail_supports_list_payloads(self) -> None:
        payload = [
            {"timestamp": 1, "latitude": 10.0, "longitude": 20.0},
            {"timestamp": 2, "latitude": 11.0, "longitude": 21.0},
        ]
        with patch.object(NASA_APP, "fetch_json_value", return_value=payload):
            trail = NASA_APP.fetch_trail(123)
        self.assertEqual([(point.timestamp, point.latitude, point.longitude) for point in trail], [(1, 10.0, 20.0), (2, 11.0, 21.0)])

    def test_render_details_page_keeps_details_background_when_stale(self) -> None:
        with patch.object(
            NASA_APP,
            "load_asset_candidates",
            return_value=NASA_APP.Image.new("RGB", (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT)),
        ) as load_asset_candidates:
            image = NASA_APP.render_details_page(self.build_location(), stale=True)
        self.assertEqual(image.size, (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))
        load_asset_candidates.assert_called_once_with(
            NASA_APP.DETAILS_TEMPLATE_PATH,
            NASA_APP.ERROR_TEMPLATE_PATH,
        )

    def test_render_crew_page_changes_with_page_badge(self) -> None:
        crew_page = self.build_crew_snapshot(count=4).crew[:2]
        page_one = NASA_APP.render_crew_page(crew_page, 1, 2, stale=False)
        page_two = NASA_APP.render_crew_page(crew_page, 2, 2, stale=False)
        self.assertEqual(page_one.size, (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))
        self.assertNotEqual(page_one.tobytes(), page_two.tobytes())

    def test_render_crew_page_passes_page_badge_label(self) -> None:
        crew_page = self.build_crew_snapshot(count=4).crew[:2]
        with patch.object(NASA_APP, "draw_badge") as draw_badge:
            image = NASA_APP.render_crew_page(crew_page, 2, 5, stale=False)
        self.assertEqual(image.size, (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))
        draw_badge.assert_called_once()
        self.assertEqual(draw_badge.call_args.args[2], "2/5")

    def test_build_pages_keeps_overflow_crew_pages(self) -> None:
        crew_snapshot = self.build_crew_snapshot(count=4)
        location = self.build_location()
        pages = NASA_APP.build_pages(
            location,
            crew_snapshot,
            map_stale=False,
            details_stale=False,
            crew_stale=False,
        )
        self.assertEqual([page.kind for page in pages], ["map", "details", "crew", "crew"])

    def test_paginate_crew_uses_two_people_per_page(self) -> None:
        crew_pages = NASA_APP.paginate_crew(self.build_crew_snapshot(count=4).crew)
        self.assertEqual(len(crew_pages), 2)
        self.assertTrue(all(len(page) == 2 for page in crew_pages))

    def test_render_single_page_supports_loading_page(self) -> None:
        loading_image = NASA_APP.Image.new("RGB", (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))
        with patch.object(NASA_APP, "render_loading_page", return_value=loading_image) as render_loading_page:
            image = NASA_APP.render_single_page("loading", [])
        self.assertIs(image, loading_image)
        render_loading_page.assert_called_once_with("render")

    def test_build_live_location_keeps_details_fresh_for_partial_enrichment_fallbacks(self) -> None:
        cached = self.build_location()
        live_position = NASA_APP.LocationSnapshot(
            source="open-notify",
            fetched_at=10,
            position_timestamp=11,
            latitude=51.5,
            longitude=-0.12,
            altitude_km=None,
            velocity_kmh=None,
            country_code="",
            country_name="",
            location_label="",
            visibility="",
            trail=[],
            details_timestamp=11,
        )
        with patch.object(NASA_APP, "build_open_notify_location", return_value=live_position):
            with patch.object(NASA_APP, "fetch_json", return_value={}):
                with patch.object(NASA_APP, "resolve_geoapify_location", return_value=("GB", "United Kingdom", "", True)):
                    with patch.object(NASA_APP, "fetch_trail", return_value=[]):
                        location, map_stale, details_stale = NASA_APP.build_live_location({}, cached)
        self.assertFalse(map_stale)
        self.assertFalse(details_stale)
        self.assertEqual(location.altitude_km, cached.altitude_km)
        self.assertEqual(location.velocity_kmh, cached.velocity_kmh)
        self.assertEqual(location.visibility, cached.visibility)
        self.assertEqual(location.country_name, "United Kingdom")

    def test_resolve_location_prefers_open_notify_before_cache(self) -> None:
        cached = self.build_location(country_name="", location_label="")
        fallback = self.build_location(country_name="North Sea", location_label="North Sea")
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "location.json"
            cache_path.write_text(NASA_APP.json.dumps(NASA_APP.serialize_location(cached)), encoding="utf-8")
            with patch.object(NASA_APP, "build_live_location", side_effect=RuntimeError("live down")):
                with patch.object(NASA_APP, "build_fallback_location", return_value=(fallback, False, True)) as build_fallback_location:
                    location, location_ok, map_stale, details_stale = NASA_APP.resolve_location({}, cache_path, False)
        self.assertTrue(location_ok)
        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.latitude, fallback.latitude)
        self.assertEqual(location.longitude, fallback.longitude)
        self.assertFalse(map_stale)
        self.assertTrue(details_stale)
        build_fallback_location.assert_called_once_with(cached)

    def test_run_health_check_returns_failure_when_any_endpoint_is_unavailable(self) -> None:
        healthy_position = (1.0, 2.0, 3)
        with patch.object(NASA_APP, "probe_open_notify_position", return_value=(NASA_APP.HealthCheckResult("open-notify-position", "healthy", "ok"), healthy_position)):
            with patch.object(NASA_APP, "probe_wtia_satellite", return_value=(NASA_APP.HealthCheckResult("wheretheiss-satellite", "healthy", "ok"), {"latitude": 1.0, "longitude": 2.0, "timestamp": 3})):
                with patch.object(NASA_APP, "probe_geoapify_reverse", return_value=NASA_APP.HealthCheckResult("geoapify-reverse", "healthy", "ok")):
                    with patch.object(NASA_APP, "probe_wtia_positions", return_value=NASA_APP.HealthCheckResult("wheretheiss-positions", "unavailable", "timeout")):
                        with patch.object(NASA_APP, "probe_crew_endpoint", side_effect=[
                            NASA_APP.HealthCheckResult("corquaid-crew", "healthy", "ok"),
                            NASA_APP.HealthCheckResult("open-notify-crew", "healthy", "ok"),
                        ]):
                            exit_code = NASA_APP.run_health_check()
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()


