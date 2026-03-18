"""Shared RGB565 conversion and framebuffer write helpers."""

from __future__ import annotations

import mmap
from pathlib import Path
from typing import Any


def rgb888_to_rgb565(image: Any) -> bytes:
    """Convert a PIL-compatible RGB image to little-endian RGB565 bytes."""
    rgb = image.convert("RGB").tobytes()
    payload = bytearray((len(rgb) // 3) * 2)
    out_idx = 0
    for idx in range(0, len(rgb), 3):
        value = ((rgb[idx] & 0xF8) << 8) | ((rgb[idx + 1] & 0xFC) << 3) | (rgb[idx + 2] >> 3)
        payload[out_idx] = value & 0xFF
        payload[out_idx + 1] = (value >> 8) & 0xFF
        out_idx += 2
    return bytes(payload)


def framebuffer_payload(image: Any, width: int, height: int) -> bytes:
    payload = rgb888_to_rgb565(image)
    expected = width * height * 2
    if len(payload) != expected:
        raise RuntimeError(f"Framebuffer payload size mismatch: expected {expected} bytes, got {len(payload)} bytes")
    return payload


def write_framebuffer(image: Any, fbdev: str, width: int, height: int) -> None:
    payload = framebuffer_payload(image, width, height)
    expected = width * height * 2
    with open(fbdev, "r+b", buffering=0) as framebuffer:
        mapping = mmap.mmap(framebuffer.fileno(), expected, access=mmap.ACCESS_WRITE)
        try:
            mapping.seek(0)
            mapping.write(payload)
        finally:
            mapping.close()


class FramebufferWriter:
    def __init__(self, fbdev: str, width: int, height: int) -> None:
        self.fbdev = fbdev
        self.width = width
        self.height = height
        self.expected = width * height * 2
        self._handle: Any | None = None
        self._mapping: mmap.mmap | None = None

    def open(self) -> None:
        handle = open(self.fbdev, "r+b", buffering=0)
        try:
            mapping = mmap.mmap(handle.fileno(), self.expected, access=mmap.ACCESS_WRITE)
        except Exception:
            handle.close()
            raise
        self._handle = handle
        self._mapping = mapping

    def write_frame(self, image: Any) -> None:
        if self._mapping is None:
            raise RuntimeError("Framebuffer is not open")
        payload = framebuffer_payload(image, self.width, self.height)
        self._mapping.seek(0)
        self._mapping.write(payload)

    def write_region(self, image: Any, left: int, top: int) -> None:
        if self._mapping is None:
            raise RuntimeError("Framebuffer is not open")
        payload = rgb888_to_rgb565(image)
        row_bytes = image.width * 2
        for row in range(image.height):
            start = row * row_bytes
            end = start + row_bytes
            offset = (((top + row) * self.width) + left) * 2
            self._mapping.seek(offset)
            self._mapping.write(payload[start:end])

    def clear(self) -> None:
        if self._mapping is None:
            raise RuntimeError("Framebuffer is not open")
        self._mapping.seek(0)
        self._mapping.write(b"\x00" * self.expected)

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "FramebufferWriter":
        self.open()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()


def framebuffer_exists(fbdev: str) -> bool:
    return Path(fbdev).exists()
