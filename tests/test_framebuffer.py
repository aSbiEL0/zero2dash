from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framebuffer import framebuffer_payload, rgb888_to_rgb565


class _FakeImage:
    def __init__(self, rgb: bytes, width: int, height: int) -> None:
        self._rgb = rgb
        self.width = width
        self.height = height

    def convert(self, mode: str) -> "_FakeImage":
        if mode != "RGB":
            raise AssertionError(f"Unexpected mode conversion: {mode}")
        return self

    def tobytes(self) -> bytes:
        return self._rgb


class FramebufferTests(unittest.TestCase):
    def test_rgb888_to_rgb565_encodes_primary_colors(self) -> None:
        image = _FakeImage(
            bytes(
                [
                    255, 0, 0,
                    0, 255, 0,
                    0, 0, 255,
                    255, 255, 255,
                ]
            ),
            width=2,
            height=2,
        )
        payload = rgb888_to_rgb565(image)
        self.assertEqual(
            payload,
            bytes(
                [
                    0x00, 0xF8,
                    0xE0, 0x07,
                    0x1F, 0x00,
                    0xFF, 0xFF,
                ]
            ),
        )

    def test_framebuffer_payload_rejects_wrong_dimensions(self) -> None:
        image = _FakeImage(bytes([0, 0, 0]), width=1, height=1)
        with self.assertRaisesRegex(RuntimeError, "payload size mismatch"):
            framebuffer_payload(image, width=2, height=1)


if __name__ == "__main__":
    unittest.main()
