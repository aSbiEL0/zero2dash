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


if __name__ == "__main__":
    unittest.main()
