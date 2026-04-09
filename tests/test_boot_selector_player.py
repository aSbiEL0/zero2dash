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

    def test_normalize_player_command_rewrites_deprecated_shell_wrapper(self) -> None:
        command, was_normalized = boot_selector.normalize_player_command("/home/pihole/zero2dash/player.sh")

        self.assertTrue(was_normalized)
        self.assertEqual(command, boot_selector.CANONICAL_PLAYER_COMMAND)

    def test_deprecated_player_shell_wrapper_falls_back_to_python_player(self) -> None:
        args = self._args()
        args.player_command = "/home/pihole/zero2dash/player.sh"

        args.player_command, was_normalized = boot_selector.normalize_player_command(args.player_command)
        registry = boot_selector.build_app_registry(args)

        self.assertTrue(was_normalized)
        self.assertEqual(registry[boot_selector.APP_ID_CREDITS].launch_command, tuple(boot_selector.player_command_args(boot_selector.CANONICAL_PLAYER_COMMAND)))
        self.assertEqual(registry[boot_selector.APP_ID_LOCKED_CONTENT_PLAYER].launch_command, tuple(boot_selector.player_command_args(boot_selector.CANONICAL_PLAYER_COMMAND)))


if __name__ == "__main__":
    unittest.main()
