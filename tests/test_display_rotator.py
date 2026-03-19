from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import threading
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
rotator_touch = _load_module("rotator_touch_test", "rotator/touch.py")


def _touch_event(ev_type: int, ev_code: int, ev_value: int) -> bytes:
    return rotator_touch.INPUT_EVENT_STRUCT.pack(0, 0, ev_type, ev_code, ev_value)


def _touch_stream(*events: tuple[int, int, int]) -> list[bytes]:
    return [_touch_event(*event) for event in events]


class _FakeInputFile:
    def __init__(self, payloads: list[bytes]) -> None:
        self._payloads = payloads

    def read(self, size: int) -> bytes:
        if self._payloads:
            return self._payloads.pop(0)
        return b""

    def __enter__(self) -> "_FakeInputFile":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _CommandRecorder:
    def __init__(self, stop_evt: threading.Event, stop_on: str) -> None:
        self.stop_evt = stop_evt
        self.stop_on = stop_on
        self.commands: list[str] = []

    def put(self, item: str) -> None:
        self.commands.append(item)
        if item == self.stop_on:
            self.stop_evt.set()


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

    def test_touch_worker_emits_main_menu_after_long_press(self) -> None:
        fake_input = _FakeInputFile(
            _touch_stream(
                (rotator_touch.EV_ABS, rotator_touch.ABS_X, 12),
                (rotator_touch.EV_ABS, rotator_touch.ABS_Y, 34),
                (rotator_touch.EV_KEY, rotator_touch.BTN_TOUCH, 1),
                (rotator_touch.EV_KEY, rotator_touch.BTN_TOUCH, 0),
            )
        )
        stop_evt = threading.Event()
        commands = _CommandRecorder(stop_evt, "MAIN_MENU")

        with patch.object(rotator_touch, "select_touch_device", return_value="/dev/input/event0"), \
            patch.object(rotator_touch.touch_calibration, "applies_to", return_value=False), \
            patch.object(rotator_touch, "detect_touch_width", return_value=(100, 0)), \
            patch.object(rotator_touch.select, "select", side_effect=lambda *_args, **_kwargs: ([fake_input], [], [])), \
            patch("builtins.open", return_value=fake_input), \
            patch.object(rotator_touch.time, "monotonic", side_effect=[0.0, 3.5]):
            thread = threading.Thread(
                target=rotator_touch.touch_worker,
                args=(commands, stop_evt, 100, 0.2),
                daemon=True,
            )
            thread.start()
            thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(commands.commands, ["MAIN_MENU"])

    def test_touch_worker_still_emits_toggle_screen_on_double_tap(self) -> None:
        fake_input = _FakeInputFile(
            _touch_stream(
                (rotator_touch.EV_ABS, rotator_touch.ABS_X, 12),
                (rotator_touch.EV_ABS, rotator_touch.ABS_Y, 34),
                (rotator_touch.EV_KEY, rotator_touch.BTN_TOUCH, 1),
                (rotator_touch.EV_KEY, rotator_touch.BTN_TOUCH, 0),
                (rotator_touch.EV_ABS, rotator_touch.ABS_X, 12),
                (rotator_touch.EV_ABS, rotator_touch.ABS_Y, 34),
                (rotator_touch.EV_KEY, rotator_touch.BTN_TOUCH, 1),
                (rotator_touch.EV_KEY, rotator_touch.BTN_TOUCH, 0),
            )
        )
        stop_evt = threading.Event()
        commands = _CommandRecorder(stop_evt, "TOGGLE_SCREEN")

        with patch.object(rotator_touch, "select_touch_device", return_value="/dev/input/event0"), \
            patch.object(rotator_touch.touch_calibration, "applies_to", return_value=False), \
            patch.object(rotator_touch, "detect_touch_width", return_value=(100, 0)), \
            patch.object(rotator_touch.select, "select", side_effect=lambda *_args, **_kwargs: ([fake_input], [], [])), \
            patch("builtins.open", return_value=fake_input), \
            patch.object(rotator_touch.time, "monotonic", side_effect=[0.0, 0.1, 0.2, 0.3]):
            thread = threading.Thread(
                target=rotator_touch.touch_worker,
                args=(commands, stop_evt, 100, 0.2),
                daemon=True,
            )
            thread.start()
            thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        self.assertIn("TOGGLE_SCREEN", commands.commands)

    def test_touch_worker_accepts_abs_syn_fallback_without_btn_touch(self) -> None:
        fake_input = _FakeInputFile(
            _touch_stream(
                (rotator_touch.EV_ABS, rotator_touch.ABS_X, 12),
                (rotator_touch.EV_ABS, rotator_touch.ABS_Y, 34),
                (rotator_touch.EV_SYN, 0, 0),
            )
        )
        stop_evt = threading.Event()
        commands = _CommandRecorder(stop_evt, "PREV")

        with patch.object(rotator_touch, "select_touch_device", return_value="/dev/input/event0"), \
            patch.object(rotator_touch.touch_calibration, "applies_to", return_value=False), \
            patch.object(rotator_touch, "detect_touch_width", return_value=(100, 0)), \
            patch.object(rotator_touch.select, "select", side_effect=lambda *_args, **_kwargs: ([fake_input], [], []) if fake_input._payloads else ([], [], [])), \
            patch("builtins.open", return_value=fake_input), \
            patch.object(rotator_touch.time, "monotonic", side_effect=[0.0, 0.5]):
            thread = threading.Thread(
                target=rotator_touch.touch_worker,
                args=(commands, stop_evt, 100, 0.2),
                daemon=True,
            )
            thread.start()
            thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(commands.commands, ["PREV"])

    def test_activate_boot_selector_requests_parent_menu_when_shell_managed(self) -> None:
        result = types.SimpleNamespace(returncode=0, stderr="", stdout="")

        with patch.dict(os.environ, {"ZERO2DASH_PARENT_SHELL": "1"}, clear=False), \
            patch.object(display_rotator, "PARENT_SHELL_MODE_REQUEST_PATH", "/tmp/zero2dash-shell-mode-request"), \
            patch.object(display_rotator.subprocess, "run", return_value=result) as run_mock:
            rc = display_rotator.activate_boot_selector()

        self.assertEqual(rc, 0)
        self.assertEqual(
            run_mock.call_args.args[0],
            [
                sys.executable,
                "-u",
                str(display_rotator.BOOT_SELECTOR_SCRIPT),
                "--request-mode",
                "menu",
                "--mode-request-path",
                "/tmp/zero2dash-shell-mode-request",
            ],
        )


if __name__ == "__main__":
    unittest.main()
