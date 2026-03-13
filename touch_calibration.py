from __future__ import annotations

import os
from pathlib import Path


FBDEV = os.environ.get("FB_DEVICE", "/dev/fb1")
TOUCH_DEVICE = os.environ.get("TOUCH_DEVICE", "/dev/input/event0")
WIDTH = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT = int(os.environ.get("FB_HEIGHT", "240"))

RAW_X_LEFT = int(os.environ.get("TOUCH_RAW_X_LEFT", "300"))
RAW_X_RIGHT = int(os.environ.get("TOUCH_RAW_X_RIGHT", "3748"))
RAW_Y_TOP = int(os.environ.get("TOUCH_RAW_Y_TOP", "3880"))
RAW_Y_BOTTOM = int(os.environ.get("TOUCH_RAW_Y_BOTTOM", "360"))


def applies_to(device_path: str) -> bool:
    return Path(device_path).name == Path(TOUCH_DEVICE).name


def _scale(value: int, raw_min: int, raw_max: int, size: int) -> int:
    if size <= 1 or raw_min == raw_max:
        return 0
    pixel = round((value - raw_min) * (size - 1) / (raw_max - raw_min))
    return max(0, min(size - 1, pixel))


def map_to_screen(raw_x: int, raw_y: int, *, width: int, height: int) -> tuple[int, int]:
    screen_x = _scale(raw_y, RAW_X_LEFT, RAW_X_RIGHT, width)
    screen_y = _scale(raw_x, RAW_Y_TOP, RAW_Y_BOTTOM, height)
    return screen_x, screen_y
