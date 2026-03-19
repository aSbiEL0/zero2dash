import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "nasa-app" / "app.py"
SPEC = importlib.util.spec_from_file_location("nasa_app_module", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
NASA_APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = NASA_APP
SPEC.loader.exec_module(NASA_APP)

SPEC.loader.exec_module(NASA_APP)


class NasaAppTests(unittest.TestCase):
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

    def test_details_page_renders_visibility_and_reason(self) -> None:
        location = NASA_APP.LocationSnapshot(
            source="test",
            fetched_at=1,
            position_timestamp=2,
            latitude=51.5,
            longitude=-0.12,
            altitude_km=408.4,
            velocity_kmh=27600.0,
            country_code="GB",
            country_name="United Kingdom",
            location_label="United Kingdom",
            visibility="Daylight",
            trail=[],
            details_timestamp=2,
        )
        image = NASA_APP.render_details_page(
            location,
            NASA_APP.ObserverConfig(lat=53.0, lon=-2.0),
            "Expedition 72 | Commander",
            stale=True,
        )
        self.assertEqual(image.size, (NASA_APP.CANVAS_WIDTH, NASA_APP.CANVAS_HEIGHT))

    def test_build_pages_keeps_overflow_crew_pages(self) -> None:
        crew_snapshot = NASA_APP.CrewSnapshot(
            source="test",
            fetched_at=1,
            crew=[
                NASA_APP.CrewMember(f"Crew {index}", "Astronaut", "ISS", "NASA", None, None, None, "Astronaut | ISS")
                for index in range(4)
            ],
            expedition="Expedition 72",
            expedition_reason="Expedition 72 | Commander",
        )
        location = NASA_APP.LocationSnapshot(
            source="test",
            fetched_at=1,
            position_timestamp=2,
            latitude=51.5,
            longitude=-0.12,
            altitude_km=408.4,
            velocity_kmh=27600.0,
            country_code="GB",
            country_name="United Kingdom",
            location_label="United Kingdom",
            visibility="Daylight",
            trail=[],
            details_timestamp=2,
        )
        pages = NASA_APP.build_pages(
            location,
            crew_snapshot,
            NASA_APP.ObserverConfig(lat=53.0, lon=-2.0),
            map_stale=False,
            details_stale=False,
            crew_stale=False,
        )
        self.assertEqual([page.kind for page in pages], ["map", "details", "crew", "crew"])


if __name__ == "__main__":
    unittest.main()

