from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types
import unittest
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


sys.modules.setdefault("fcntl", types.SimpleNamespace(ioctl=lambda *args, **kwargs: None))
class _DummyImageModule:
    LANCZOS = 1
    Resampling = types.SimpleNamespace(LANCZOS=1)


sys.modules.setdefault("PIL", types.SimpleNamespace(Image=_DummyImageModule, ImageSequence=types.SimpleNamespace(Iterator=lambda _gif: [])))
boot_selector = _load_module("boot_selector", "boot/boot_selector.py")


class BootSelectorTests(unittest.TestCase):
    def _valid_args(self, **overrides):
        values = {
            "width": 320,
            "height": 240,
            "touch_settle_secs": 0.35,
            "touch_debounce_secs": 0.35,
            "gif_speed": 0.5,
            "shutdown_command": "systemctl poweroff",
            "pin": "0123",
            "player_command": "player.sh",
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_main_menu_quadrants_map_to_expected_actions(self) -> None:
        self.assertEqual(boot_selector.resolve_main_menu_action(10, 10, 320, 240), boot_selector.MAIN_MENU_HOME)
        self.assertEqual(boot_selector.resolve_main_menu_action(300, 10, 320, 240), boot_selector.MAIN_MENU_INFO)
        self.assertEqual(boot_selector.resolve_main_menu_action(10, 200, 320, 240), boot_selector.MAIN_MENU_PADLOCK)
        self.assertEqual(boot_selector.resolve_main_menu_action(300, 200, 320, 240), boot_selector.MAIN_MENU_SHUTDOWN)

    def test_day_night_vertical_mapping_obeys_invert_flag(self) -> None:
        self.assertEqual(boot_selector.resolve_day_night_action(20, 240, False), boot_selector.DAY_NIGHT_DAY)
        self.assertEqual(boot_selector.resolve_day_night_action(220, 240, False), boot_selector.DAY_NIGHT_NIGHT)
        self.assertEqual(boot_selector.resolve_day_night_action(20, 240, True), boot_selector.DAY_NIGHT_NIGHT)
        self.assertEqual(boot_selector.resolve_day_night_action(220, 240, True), boot_selector.DAY_NIGHT_DAY)

    def test_shutdown_vertical_mapping_obeys_invert_flag(self) -> None:
        self.assertEqual(boot_selector.resolve_shutdown_action(20, 240, False), boot_selector.SHUTDOWN_CONFIRM)
        self.assertEqual(boot_selector.resolve_shutdown_action(220, 240, False), boot_selector.SHUTDOWN_CANCEL)
        self.assertEqual(boot_selector.resolve_shutdown_action(20, 240, True), boot_selector.SHUTDOWN_CANCEL)
        self.assertEqual(boot_selector.resolve_shutdown_action(220, 240, True), boot_selector.SHUTDOWN_CONFIRM)

    def test_keypad_grid_maps_digits_and_actions(self) -> None:
        self.assertEqual(boot_selector.resolve_keypad_action(10, 10, 320, 240), "1")
        self.assertEqual(boot_selector.resolve_keypad_action(90, 10, 320, 240), "2")
        self.assertEqual(boot_selector.resolve_keypad_action(170, 10, 320, 240), "3")
        self.assertEqual(boot_selector.resolve_keypad_action(250, 10, 320, 240), boot_selector.KEYPAD_OK)
        self.assertEqual(boot_selector.resolve_keypad_action(250, 120, 320, 240), "0")
        self.assertEqual(boot_selector.resolve_keypad_action(250, 220, 320, 240), boot_selector.KEYPAD_NO)

    def test_shutdown_command_is_split_safely(self) -> None:
        command = boot_selector.shutdown_command_args('shutdown --message "night mode" now')
        self.assertEqual(command, ["shutdown", "--message", "night mode", "now"])

    def test_player_command_is_split_safely(self) -> None:
        command = boot_selector.player_command_args('player.sh --pin "0123"')
        self.assertEqual(command, ["player.sh", "--pin", "0123"])

    def test_validate_args_rejects_missing_pin(self) -> None:
        self.assertEqual(boot_selector.validate_args(self._valid_args(pin="")), 1)

    def test_validate_args_rejects_missing_player_command(self) -> None:
        self.assertEqual(boot_selector.validate_args(self._valid_args(player_command="   ")), 1)

    def test_evaluate_pin_entry_preserves_leading_zero_pin(self) -> None:
        result, failures = boot_selector.evaluate_pin_entry("0123", "0123", 2)
        self.assertEqual(result, "success")
        self.assertEqual(failures, 0)

    def test_evaluate_pin_entry_returns_retry_before_third_failure(self) -> None:
        result, failures = boot_selector.evaluate_pin_entry("9999", "0123", 1)
        self.assertEqual(result, "retry")
        self.assertEqual(failures, 2)

    def test_evaluate_pin_entry_triggers_shutdown_on_third_failure(self) -> None:
        result, failures = boot_selector.evaluate_pin_entry("9999", "0123", 2)
        self.assertEqual(result, "shutdown")
        self.assertEqual(failures, 3)

    def test_launch_service_uses_direct_fallback_outside_systemd(self) -> None:
        calls: list[str] = []
        original_invocation_id = os.environ.pop("INVOCATION_ID", None)
        original_launcher = boot_selector._launch_direct_mode
        try:
            boot_selector._launch_direct_mode = lambda service_name: calls.append(service_name) or 0
            rc = boot_selector.launch_service("display.service")
        finally:
            boot_selector._launch_direct_mode = original_launcher
            if original_invocation_id is not None:
                os.environ["INVOCATION_ID"] = original_invocation_id
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["display.service"])

    def test_run_shutdown_executes_configured_command(self) -> None:
        calls: list[list[str]] = []

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        original_run = boot_selector.subprocess.run
        try:
            boot_selector.subprocess.run = lambda command, check, capture_output, text: calls.append(command) or Result()
            rc = boot_selector.run_shutdown('echo "bye now"')
        finally:
            boot_selector.subprocess.run = original_run
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [["echo", "bye now"]])

    def test_run_player_executes_configured_command(self) -> None:
        calls: list[list[str]] = []

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        original_run = boot_selector.subprocess.run
        try:
            boot_selector.subprocess.run = lambda command, check, capture_output, text: calls.append(command) or Result()
            rc = boot_selector.run_player('player.sh "0123"')
        finally:
            boot_selector.subprocess.run = original_run
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [["player.sh", "0123"]])


if __name__ == "__main__":
    unittest.main()
