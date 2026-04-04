from __future__ import annotations

import unittest
from types import SimpleNamespace

from boot import boot_selector


class BootSelectorPlayerContractTests(unittest.TestCase):
    def _args(self) -> SimpleNamespace:
        return SimpleNamespace(
            day_service="display.service",
            night_service="night.service",
            nasa_command="python3 -u /tmp/nasa.py",
            mode_request_path="/tmp/zero2dash-shell-mode-request",
            player_command="python3 -u /tmp/player.py",
        )

    def test_theme_assets_require_player_assets(self) -> None:
        self.assertIn("player.png", boot_selector.THEME_REQUIRED_FILES)
        self.assertIn("overlay.png", boot_selector.THEME_REQUIRED_FILES)

    def test_credits_launches_player_child_in_credits_mode(self) -> None:
        registry = boot_selector.build_app_registry(self._args())
        app = registry[boot_selector.APP_ID_CREDITS]

        self.assertEqual(app.kind, boot_selector.APP_KIND_CHILD_PROCESS)
        self.assertEqual(app.launch_command, ("python3", "-u", "/tmp/player.py"))
        self.assertTrue(app.supports_home_gesture)
        self.assertFalse(app.shell_handles_home_gesture)
        self.assertIn(("ZERO2DASH_PLAYER_MODE", "credits"), app.env_overrides)

    def test_vault_launches_same_player_child_in_vault_mode(self) -> None:
        registry = boot_selector.build_app_registry(self._args())
        app = registry[boot_selector.APP_ID_LOCKED_CONTENT_PLAYER]

        self.assertEqual(app.kind, boot_selector.APP_KIND_CHILD_PROCESS)
        self.assertEqual(app.launch_command, ("python3", "-u", "/tmp/player.py"))
        self.assertTrue(app.supports_home_gesture)
        self.assertFalse(app.shell_handles_home_gesture)
        self.assertIn(("ZERO2DASH_PLAYER_MODE", "vault"), app.env_overrides)

    def test_validate_args_rejects_deprecated_player_shell_wrapper(self) -> None:
        args = self._args()
        args.width = 320
        args.height = 240
        args.touch_settle_secs = 0.35
        args.touch_debounce_secs = 0.35
        args.child_stop_grace_secs = 3.0
        args.home_gesture_hold_secs = 2.0
        args.home_gesture_corner_width = 64
        args.home_gesture_corner_height = 48
        args.gif_speed = 0.5
        args.shutdown_command = "systemctl poweroff"
        args.player_command = "/home/pihole/zero2dash/player.sh"

        self.assertEqual(boot_selector.validate_args(args), 1)


if __name__ == "__main__":
    unittest.main()
