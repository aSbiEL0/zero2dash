from __future__ import annotations

import importlib.util
import tempfile
import types
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


boot_selector = _load_module("boot_selector_test", "boot/boot_selector.py")


class _FakeChildManager:
    def __init__(self, *, start_result: bool = True) -> None:
        self.start_result = start_result
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.shutdown_calls = 0

    def start_app(self, app) -> bool:
        self.started.append(app.id)
        return self.start_result

    def stop_current(self, reason: str) -> bool:
        self.stopped.append(reason)
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def running_app(self):
        return None


class _WriteFrameOnlyFramebuffer:
    def __init__(self) -> None:
        self.frames = []

    def write_frame(self, image) -> None:
        self.frames.append(image)


class _FakeInputFile:
    def __init__(self, events: list[tuple[int, int, int]]) -> None:
        payload = bytearray()
        for ev_type, ev_code, ev_value in events:
            payload.extend(boot_selector.INPUT_EVENT_STRUCT.pack(0, 0, ev_type, ev_code, ev_value))
        self._payload = bytes(payload)
        self._offset = 0

    def read(self, size: int) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += size
        return chunk

    def close(self) -> None:
        return None


class BootSelectorTests(unittest.TestCase):
    def _touch_theme(self, root: Path, theme_id: str, *, missing: set[str] | None = None) -> Path:
        missing = missing or set()
        theme_dir = root / theme_id
        theme_dir.mkdir(parents=True, exist_ok=True)
        for asset_name in sorted(boot_selector.THEME_REQUIRED_FILES):
            if asset_name in missing:
                continue
            (theme_dir / asset_name).touch()
        return theme_dir

    def test_theme_catalog_discovers_valid_themes_and_rejects_missing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            theme_root = Path(temp_dir)
            self._touch_theme(theme_root, "default")
            self._touch_theme(theme_root, "broken", missing={"denied.gif"})

            catalog = boot_selector.load_theme_catalog(theme_root)

            self.assertEqual(sorted(catalog), ["default"])
            self.assertEqual(boot_selector.validate_theme_selection("missing", catalog), "default")

    def test_theme_catalog_raises_when_no_valid_themes_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            theme_root = Path(temp_dir)
            self._touch_theme(theme_root, "broken", missing={"granted.gif"})
            self._touch_theme(theme_root, "also-broken", missing={"denied.gif", "granted.gif"})

            with self.assertRaisesRegex(RuntimeError, "No valid themes found"):
                boot_selector.load_theme_catalog(theme_root)

    def test_theme_state_store_round_trips_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            theme_path = Path(temp_dir) / "theme.txt"
            store = boot_selector.ThemeStateStore(theme_path)

            self.assertIsNone(store.read_theme_id())
            store.write_theme_id("comic")
            self.assertEqual(store.read_theme_id(), "comic")

    def test_theme_state_store_ignores_persist_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            theme_path = Path(temp_dir) / "theme.txt"
            store = boot_selector.ThemeStateStore(theme_path)

            with mock.patch.object(boot_selector.os, "replace", side_effect=PermissionError("nope")):
                store.write_theme_id("comic")

            self.assertFalse(theme_path.exists())

    def test_screen_image_returns_named_screen(self) -> None:
        marker = object()
        shell_images = types.SimpleNamespace(screens={boot_selector.ROOT_MENU_1: marker})

        self.assertIs(boot_selector._screen_image(shell_images, boot_selector.ROOT_MENU_1), marker)

    def test_touch_calibration_infers_swapped_axes_from_corner_taps(self) -> None:
        calibration = boot_selector.touch_calibration.infer_from_corner_taps(
            "/dev/input/event0",
            {
                "top_left": (3800, 300),
                "top_right": (3800, 3700),
                "bottom_left": (400, 300),
                "bottom_right": (400, 3700),
            },
        )

        self.assertTrue(calibration.swap_axes)
        self.assertEqual(
            boot_selector.touch_calibration.map_to_screen(3800, 300, width=320, height=240, calibration=calibration),
            (0, 0),
        )
        self.assertEqual(
            boot_selector.touch_calibration.map_to_screen(400, 3700, width=320, height=240, calibration=calibration),
            (319, 239),
        )

    def test_screen_action_routes_root_and_child_screens(self) -> None:
        w = 320
        h = 240
        cases = [
            (boot_selector.ROOT_MENU_1, 0, 120, boot_selector.ROOT_MENU_2),
            (boot_selector.ROOT_MENU_1, 30, 20, "dashboards"),
            (boot_selector.ROOT_MENU_1, 220, 20, "photos"),
            (boot_selector.ROOT_MENU_1, 30, 180, "iss"),
            (boot_selector.ROOT_MENU_1, 220, 180, "locked_content"),
            (boot_selector.ROOT_MENU_2, 0, 120, boot_selector.ROOT_MENU_1),
            (boot_selector.ROOT_MENU_2, 30, 20, "credits"),
            (boot_selector.ROOT_MENU_2, 220, 20, "themes"),
            (boot_selector.ROOT_MENU_2, 30, 180, "settings"),
            (boot_selector.ROOT_MENU_2, 220, 180, "shutdown"),
            (boot_selector.DASHBOARDS_MENU, 0, 120, boot_selector.ROOT_MENU_1),
            (boot_selector.DASHBOARDS_MENU, 30, 20, "dashboards"),
            (boot_selector.DASHBOARDS_MENU, 30, 180, "night"),
            (boot_selector.SETTINGS_MENU, 0, 120, boot_selector.ROOT_MENU_2),
            (boot_selector.SETTINGS_MENU, 30, 20, "network"),
            (boot_selector.SETTINGS_MENU, 30, 110, "pi_stats"),
            (boot_selector.SETTINGS_MENU, 30, 210, "logs"),
            (boot_selector.SHUTDOWN_CONFIRM, 0, 120, "cancel"),
            (boot_selector.SHUTDOWN_CONFIRM, 30, 20, "confirm"),
            (boot_selector.SHUTDOWN_CONFIRM, 30, 180, "cancel"),
            (boot_selector.THEMES_MENU, 0, 120, boot_selector.ROOT_MENU_2),
            (boot_selector.THEMES_MENU, 30, 20, "default"),
            (boot_selector.THEMES_MENU, 140, 20, "steele"),
            (boot_selector.THEMES_MENU, 250, 20, "comic"),
            (boot_selector.NETWORK_STATUS, 0, 120, boot_selector.SETTINGS_MENU),
            (boot_selector.NETWORK_STATUS, 30, 120, None),
            (boot_selector.PI_STATS_STATUS, 0, 120, boot_selector.SETTINGS_MENU),
            (boot_selector.LOGS_STATUS, 0, 120, boot_selector.SETTINGS_MENU),
            (boot_selector.ISS_PLACEHOLDER, 0, 120, boot_selector.ROOT_MENU_1),
            (boot_selector.ISS_PLACEHOLDER, 30, 120, None),
        ]

        for screen_name, x, y, expected in cases:
            with self.subTest(screen_name=screen_name, x=x, y=y):
                self.assertEqual(
                    boot_selector.resolve_screen_action(screen_name, x, y, w, h),
                    expected,
                )

    def test_keypad_mapping_and_pin_evaluation(self) -> None:
        w = 320
        h = 240
        self.assertEqual(boot_selector.resolve_keypad_action(5, 5, w, h), "1")
        self.assertEqual(boot_selector.resolve_keypad_action(120, 100, w, h), "5")
        self.assertEqual(boot_selector.resolve_keypad_action(300, 20, w, h), "ok")
        self.assertEqual(boot_selector.resolve_keypad_action(300, 100, w, h), "0")
        self.assertEqual(boot_selector.resolve_keypad_action(300, 190, w, h), "cancel")
        self.assertEqual(boot_selector.resolve_keypad_action(160, 190, w, h), "8")

        self.assertEqual(boot_selector.evaluate_pin_entry("1234", "1234", 2), ("success", 0))
        self.assertEqual(boot_selector.evaluate_pin_entry("1111", "1234", 0), ("retry", 1))
        self.assertEqual(boot_selector.evaluate_pin_entry("1111", "1234", 2), ("shutdown", 3))

    def test_pin_failures_only_persist_for_immediate_locked_content_retries(self) -> None:
        self.assertFalse(boot_selector.should_reset_pin_failures(boot_selector.ROOT_MENU_1, boot_selector.APP_ID_LOCKED_CONTENT))
        self.assertTrue(boot_selector.should_reset_pin_failures(boot_selector.ROOT_MENU_1, "photos"))
        self.assertTrue(boot_selector.should_reset_pin_failures(boot_selector.PIN_KEYPAD, "cancel"))
        self.assertFalse(boot_selector.should_reset_pin_failures(boot_selector.PIN_KEYPAD, "ok"))
        self.assertTrue(boot_selector.should_reset_pin_failures(boot_selector.ROOT_MENU_2, "themes"))
        self.assertTrue(boot_selector.should_reset_pin_failures(boot_selector.DASHBOARDS_MENU, None, boot_selector.SHELL_MODE_DASHBOARDS))

    def test_app_registry_and_mode_request_handling(self) -> None:
        args = types.SimpleNamespace(day_service="display.service", night_service="night.service", mode_request_path="/tmp/shell-mode")
        registry = boot_selector.build_app_registry(args)

        self.assertEqual(registry[boot_selector.APP_ID_DASHBOARDS].kind, boot_selector.APP_KIND_CHILD_PROCESS)
        self.assertEqual(registry[boot_selector.APP_ID_PHOTOS].parent_screen, boot_selector.ROOT_MENU_1)
        self.assertEqual(registry[boot_selector.APP_ID_NETWORK].preview_asset, "stats.png")
        self.assertEqual(registry[boot_selector.APP_ID_ISS].parent_screen, boot_selector.ROOT_MENU_1)
        self.assertFalse(registry[boot_selector.APP_ID_DASHBOARDS].shell_handles_home_gesture)
        self.assertTrue(registry[boot_selector.APP_ID_PHOTOS].shell_handles_home_gesture)
        self.assertIn(("BOOT_SELECTOR_MODE_REQUEST_PATH", "/tmp/shell-mode"), registry[boot_selector.APP_ID_NIGHT].env_overrides)

        snapshot = boot_selector.build_contract_snapshot(
            registry,
            registry[boot_selector.APP_ID_NIGHT],
            "request-file",
            types.SimpleNamespace(theme_root="themes", default_theme="default"),
            {"default": object(), "comic": object(), "steele": object()},
            "default",
        )
        self.assertEqual(snapshot["shell_modes"], ["menu", "dashboards", "photos", "night"])
        self.assertIn(boot_selector.ISS_PLACEHOLDER, snapshot["screens"])

        manager = _FakeChildManager(start_result=True)
        self.assertEqual(
            boot_selector.handle_mode_request(boot_selector.SHELL_MODE_MENU, registry, registry[boot_selector.APP_ID_NIGHT], manager),
            boot_selector.SHELL_MODE_MENU,
        )
        self.assertEqual(manager.stopped, ["menu mode request"])

        for requested_mode, expected_app_id in [
            (boot_selector.SHELL_MODE_DASHBOARDS, boot_selector.APP_ID_DASHBOARDS),
            (boot_selector.SHELL_MODE_PHOTOS, boot_selector.APP_ID_PHOTOS),
            (boot_selector.SHELL_MODE_NIGHT, boot_selector.APP_ID_NIGHT),
        ]:
            with self.subTest(requested_mode=requested_mode):
                manager = _FakeChildManager(start_result=True)
                result = boot_selector.handle_mode_request(requested_mode, registry, registry[boot_selector.APP_ID_NIGHT], manager)
                self.assertEqual(result, boot_selector.RUNNING_APP)
                self.assertEqual(manager.started, [expected_app_id])

        manager = _FakeChildManager(start_result=False)
        self.assertEqual(
            boot_selector.handle_mode_request(boot_selector.SHELL_MODE_DASHBOARDS, registry, registry[boot_selector.APP_ID_NIGHT], manager),
            boot_selector.SHELL_MODE_MENU,
        )
        self.assertEqual(manager.started, [boot_selector.APP_ID_DASHBOARDS])

    def test_write_framebuffer_image_accepts_write_frame_contract(self) -> None:
        framebuffer = _WriteFrameOnlyFramebuffer()

        boot_selector.write_framebuffer_image(framebuffer, object())

        self.assertEqual(len(framebuffer.frames), 1)

    def test_touch_reader_accepts_abs_syn_fallback_without_btn_touch(self) -> None:
        fake_input = _FakeInputFile(
            [
                (boot_selector.EV_ABS, boot_selector.ABS_X, 10),
                (boot_selector.EV_ABS, boot_selector.ABS_Y, 20),
                (boot_selector.EV_SYN, 0, 0),
            ]
        )

        with mock.patch.object(boot_selector, "touch_probe", return_value=("/dev/input/event0", "test")), \
            mock.patch.object(boot_selector.touch_calibration, "applies_to", return_value=False), \
            mock.patch.object(boot_selector, "detect_touch_width", return_value=(320, 0)), \
            mock.patch.object(boot_selector.select, "select", side_effect=lambda *_args, **_kwargs: ([fake_input], [], [])), \
            mock.patch("builtins.open", return_value=fake_input), \
            mock.patch.object(boot_selector.time, "monotonic", return_value=1.0):
            reader = boot_selector.TouchReader(320, 240)
            action = reader.read_action(lambda x, y: f"{x},{y}", ready_after=0.0, touch_debounce_secs=0.0, timeout_secs=None)

        self.assertEqual(action, "10,20")

    def test_wait_for_home_gesture_accepts_abs_syn_fallback(self) -> None:
        fake_input = _FakeInputFile(
            [
                (boot_selector.EV_ABS, boot_selector.ABS_X, 10),
                (boot_selector.EV_ABS, boot_selector.ABS_Y, 10),
                (boot_selector.EV_SYN, 0, 0),
            ]
        )
        select_results = iter([([fake_input], [], []), ([], [], [])])

        with mock.patch.object(boot_selector, "touch_probe", return_value=("/dev/input/event0", "test")), \
            mock.patch.object(boot_selector.touch_calibration, "applies_to", return_value=False), \
            mock.patch.object(boot_selector, "detect_touch_width", return_value=(320, 0)), \
            mock.patch.object(boot_selector.select, "select", side_effect=lambda *_args, **_kwargs: next(select_results)), \
            mock.patch("builtins.open", return_value=fake_input), \
            mock.patch.object(boot_selector.time, "monotonic", side_effect=[0.0, 0.2]):
            reader = boot_selector.TouchReader(320, 240)
            region = boot_selector.TouchRegion("menu", 0, 0, 20, 20)
            self.assertTrue(reader.wait_for_home_gesture(region, hold_secs=0.15, poll_timeout_secs=0.05))

    def test_run_main_screen_shell_routes_root_dashboard_to_dashboards_menu(self) -> None:
        labels: list[str] = []
        manager = _FakeChildManager()

        def _wait_for_shell_action_or_mode(_touch_reader, label, _resolver, _settle, _debounce, _mode_store):
            labels.append(label)
            if len(labels) == 1:
                return "dashboards", None
            boot_selector.STOP_REQUESTED = True
            return None, None

        args = types.SimpleNamespace(
            child_stop_grace_secs=1.0,
            width=320,
            height=240,
            home_gesture_corner_width=64,
            home_gesture_corner_height=48,
            home_gesture_hold_secs=1.5,
            touch_settle_secs=0.0,
            touch_debounce_secs=0.0,
            gif_speed=1.0,
            pin="",
            player_command="echo",
            shutdown_command="echo",
        )
        app_registry = {
            boot_selector.APP_ID_DASHBOARDS: types.SimpleNamespace(id=boot_selector.APP_ID_DASHBOARDS),
            boot_selector.APP_ID_PHOTOS: types.SimpleNamespace(id=boot_selector.APP_ID_PHOTOS),
            boot_selector.APP_ID_NIGHT: types.SimpleNamespace(id=boot_selector.APP_ID_NIGHT),
        }
        shell_images = types.SimpleNamespace(
            screens={
                boot_selector.ROOT_MENU_1: object(),
                boot_selector.DASHBOARDS_MENU: object(),
            },
            status_base=object(),
            granted_gif=Path("granted.gif"),
            denied_gif=Path("denied.gif"),
        )

        with mock.patch.object(boot_selector, "ChildAppManager", return_value=manager), \
            mock.patch.object(boot_selector, "wait_for_shell_action_or_mode", side_effect=_wait_for_shell_action_or_mode), \
            mock.patch.object(boot_selector, "write_framebuffer_image", return_value=None):
            boot_selector.STOP_REQUESTED = False
            rc = boot_selector.run_main_screen_shell(
                args,
                framebuffer=object(),
                touch_reader=types.SimpleNamespace(),
                mode_store=types.SimpleNamespace(consume_request=lambda: None),
                app_registry=app_registry,
                theme_catalog={},
                theme_state_store=types.SimpleNamespace(write_theme_id=lambda *_args, **_kwargs: None),
                shell_images=shell_images,
                active_theme_id="default",
            )
        boot_selector.STOP_REQUESTED = False

        self.assertEqual(rc, 1)
        self.assertEqual(labels, ["main_menu_1 selection", "dashboards_menu selection"])
        self.assertEqual(manager.started, [])


if __name__ == "__main__":
    unittest.main()
