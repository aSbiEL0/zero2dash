from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framebuffer import FramebufferWriter, framebuffer_payload, rgb888_to_rgb565, write_framebuffer


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

    def test_write_framebuffer_writes_expected_bytes(self) -> None:
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
        expected = bytes(
            [
                0x00, 0xF8,
                0xE0, 0x07,
                0x1F, 0x00,
                0xFF, 0xFF,
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            fb_path = Path(temp_dir) / "fb.bin"
            fb_path.write_bytes(b"\x00" * len(expected))

            write_framebuffer(image, str(fb_path), width=2, height=2)

            self.assertEqual(fb_path.read_bytes(), expected)

    def test_framebuffer_writer_supports_full_frame_and_regions(self) -> None:
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
        expected_full = bytes(
            [
                0x00, 0xF8,
                0xE0, 0x07,
                0x1F, 0x00,
                0xFF, 0xFF,
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            fb_path = Path(temp_dir) / "fb.bin"
            fb_path.write_bytes(b"\x00" * len(expected_full))

            with FramebufferWriter(str(fb_path), width=2, height=2) as framebuffer:
                framebuffer.write_frame(image)

            self.assertEqual(fb_path.read_bytes(), expected_full)

        with tempfile.TemporaryDirectory() as temp_dir:
            fb_path = Path(temp_dir) / "fb.bin"
            fb_path.write_bytes(b"\x00" * 32)

            with FramebufferWriter(str(fb_path), width=4, height=4) as framebuffer:
                framebuffer.write_region(image, left=1, top=1)

            expected_region = bytearray(32)
            expected_region[10:14] = expected_full[0:4]
            expected_region[18:22] = expected_full[4:8]
            self.assertEqual(fb_path.read_bytes(), bytes(expected_region))


if __name__ == "__main__":
    unittest.main()
