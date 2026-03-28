import importlib.util
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

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
        self.assertEqual(NASA_APP.location_display_name(international_waters), "International Waters")

    def test_details_page_renders_with_location_display_name_fallback(self) -> None:
        location = self.build_location(country_name="", location_label="North Sea")
        with patch.object(NASA_APP, "location_display_name", return_value="North Sea") as location_display_name:
            image = NASA_APP.render_details_page(
                location,
                "Expedition 72 | Commander",
                stale=True,
            )
        self.assertEqual(image.size, (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))
        location_display_name.assert_called_once_with(location)

    def test_render_crew_page_changes_with_page_badge(self) -> None:
        crew_page = self.build_crew_snapshot(count=4).crew[:3]
        page_one = NASA_APP.render_crew_page(crew_page, 1, 2, stale=False)
        page_two = NASA_APP.render_crew_page(crew_page, 2, 2, stale=False)
        self.assertEqual(page_one.size, (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))
        self.assertNotEqual(page_one.tobytes(), page_two.tobytes())

    def test_render_crew_page_passes_page_badge_label(self) -> None:
        crew_page = self.build_crew_snapshot(count=4).crew[:3]
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


if __name__ == "__main__":
    unittest.main()


