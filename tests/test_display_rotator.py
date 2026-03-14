from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from rotator import backoff as rotator_backoff
from rotator import config as rotator_config


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "fcntl" not in sys.modules:
    sys.modules["fcntl"] = types.SimpleNamespace(ioctl=lambda *_args, **_kwargs: None)


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


display_rotator = _load_module("display_rotator_test", "display_rotator.py")


class DisplayRotatorTests(unittest.TestCase):
    def _write_module(self, base_dir: Path, module_name: str) -> Path:
        module_dir = base_dir / "modules" / module_name
        module_dir.mkdir(parents=True, exist_ok=True)
        (module_dir / "display.py").write_text("print('ok')\n", encoding="utf-8")
        return module_dir

    def test_discover_pages_skips_photos_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self._write_module(base_dir, "pihole")
            self._write_module(base_dir, "photos")
            self._write_module(base_dir, "weather")
            (base_dir / "modules.txt").write_text("pihole\nphotos\nweather\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=False):
                pages = display_rotator.discover_pages(base_dir)

            self.assertEqual(
                pages,
                [
                    "modules/pihole/display.py",
                    "modules/weather/display.py",
                ],
            )

    def test_discover_pages_skips_photos_from_fallback_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self._write_module(base_dir, "pihole")
            self._write_module(base_dir, "photos")
            self._write_module(base_dir, "weather")

            with patch.dict(os.environ, {}, clear=False):
                pages = display_rotator.discover_pages(base_dir)

            self.assertEqual(
                pages,
                [
                    "modules/pihole/display.py",
                    "modules/weather/display.py",
                ],
            )

    def test_resolve_page_specs_applies_module_dwell_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            pihole_dir = self._write_module(base_dir, "pihole")
            weather_dir = self._write_module(base_dir, "weather")
            (weather_dir / "rotator.json").write_text(json.dumps({"dwell_secs": 21}), encoding="utf-8")

            with patch.dict(os.environ, {}, clear=False):
                specs = display_rotator.resolve_page_specs(
                    [
                        os.fspath(pihole_dir / "display.py"),
                        os.fspath(weather_dir / "display.py"),
                    ],
                    base_dir,
                    default_dwell_secs=13,
                )

            self.assertEqual(
                specs,
                [
                    (os.fspath(pihole_dir / "display.py"), 13),
                    (os.fspath(weather_dir / "display.py"), 21),
                ],
            )

    def test_invalid_module_dwell_metadata_falls_back_to_rotator_secs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            weather_dir = self._write_module(base_dir, "weather")
            (weather_dir / "rotator.json").write_text(json.dumps({"dwell_secs": "fast"}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                with patch.dict(os.environ, {}, clear=False):
                    specs = display_rotator.resolve_page_specs(
                        [os.fspath(weather_dir / "display.py")],
                        base_dir,
                        default_dwell_secs=13,
                    )

            self.assertEqual(specs, [(os.fspath(weather_dir / "display.py"), 13)])
            self.assertIn("Invalid dwell_secs", stdout.getvalue())

    def test_backoff_caps_after_configured_limit(self) -> None:
        self.assertEqual(rotator_backoff.calculate_backoff_secs(1, 300), 10)
        self.assertEqual(rotator_backoff.calculate_backoff_secs(2, 300), 30)
        self.assertEqual(rotator_backoff.calculate_backoff_secs(3, 300), 60)
        self.assertEqual(rotator_backoff.calculate_backoff_secs(4, 45), 45)

    def test_rotator_config_parsing_applies_floors(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ROTATOR_SECS": "2",
                "ROTATOR_TOUCH_WIDTH": "75",
                "ROTATOR_TAP_DEBOUNCE_SECS": "-2",
                "ROTATOR_QUARANTINE_FAILURE_THRESHOLD": "0",
                "ROTATOR_QUARANTINE_CYCLES": "0",
                "ROTATOR_BACKOFF_MAX_SECS": "0",
            },
            clear=False,
        ):
            self.assertEqual(rotator_config.parse_rotate_secs(), 5)
            self.assertEqual(rotator_config.parse_width(), 100)
            self.assertEqual(rotator_config.parse_tap_debounce(), 0.0)
            self.assertEqual(rotator_config.parse_quarantine_failure_threshold(), 1)
            self.assertEqual(rotator_config.parse_quarantine_cycles(), 1)
            self.assertEqual(rotator_config.parse_backoff_max_secs(), 1)


if __name__ == "__main__":
    unittest.main()
