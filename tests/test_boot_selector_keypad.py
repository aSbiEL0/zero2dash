from __future__ import annotations

import unittest

from PIL import Image

from boot import boot_selector


class BootSelectorKeypadFeedbackTests(unittest.TestCase):
    def test_keypad_feedback_is_only_active_on_keypad_before_expiry(self) -> None:
        self.assertTrue(boot_selector.keypad_feedback_active(boot_selector.PIN_KEYPAD, "7", 11.0, now=10.5))
        self.assertFalse(boot_selector.keypad_feedback_active(boot_selector.ROOT_MENU_1, "7", 11.0, now=10.5))
        self.assertFalse(boot_selector.keypad_feedback_active(boot_selector.PIN_KEYPAD, None, 11.0, now=10.5))
        self.assertFalse(boot_selector.keypad_feedback_active(boot_selector.PIN_KEYPAD, "7", 11.0, now=11.0))

    def test_keypad_feedback_timeout_returns_remaining_window(self) -> None:
        self.assertEqual(boot_selector.keypad_feedback_timeout(boot_selector.PIN_KEYPAD, "4", 6.0, now=5.25), 0.75)
        self.assertIsNone(boot_selector.keypad_feedback_timeout(boot_selector.PIN_KEYPAD, "4", 6.0, now=6.0))

    def test_draw_keypad_feedback_changes_image(self) -> None:
        base = Image.new("RGB", (320, 240), (0, 0, 0))

        rendered = boot_selector.draw_keypad_feedback(base, "8")

        self.assertEqual(base.getpixel((160, 24)), (0, 0, 0))
        self.assertNotEqual(rendered.getpixel((160, 24)), (0, 0, 0))

    def test_draw_shell_screen_applies_keypad_feedback_only_when_active(self) -> None:
        base = Image.new("RGB", (320, 240), (0, 0, 0))
        shell_images = boot_selector.ShellImages(
            screens={boot_selector.PIN_KEYPAD: base, boot_selector.ROOT_MENU_1: base},
            status_base=base,
            granted_gif=boot_selector.BASE_DIR / "boot" / "granted.gif",
            denied_gif=boot_selector.BASE_DIR / "boot" / "denied.gif",
        )

        keypad_frame = boot_selector.draw_shell_screen(shell_images, boot_selector.PIN_KEYPAD, keypad_digit="5", keypad_visible_until=2.0, now=1.0)
        menu_frame = boot_selector.draw_shell_screen(shell_images, boot_selector.ROOT_MENU_1, keypad_digit="5", keypad_visible_until=2.0, now=1.0)

        self.assertNotEqual(keypad_frame.getpixel((160, 24)), (0, 0, 0))
        self.assertEqual(menu_frame.getpixel((160, 24)), (0, 0, 0))

    def test_keypad_touch_mapping_remains_unchanged(self) -> None:
        self.assertEqual(boot_selector.resolve_keypad_action(10, 10, 320, 240), "1")
        self.assertEqual(boot_selector.resolve_keypad_action(250, 10, 320, 240), "ok")
        self.assertEqual(boot_selector.resolve_keypad_action(250, 200, 320, 240), "cancel")


if __name__ == "__main__":
    unittest.main()
