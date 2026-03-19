from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


FBDEV = os.environ.get("FB_DEVICE", "/dev/fb1")
TOUCH_DEVICE = os.environ.get("TOUCH_DEVICE", "/dev/input/event0")
WIDTH = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT = int(os.environ.get("FB_HEIGHT", "240"))

LEGACY_RAW_X_LEFT = int(os.environ.get("TOUCH_RAW_X_LEFT", "300"))
LEGACY_RAW_X_RIGHT = int(os.environ.get("TOUCH_RAW_X_RIGHT", "3748"))
LEGACY_RAW_Y_TOP = int(os.environ.get("TOUCH_RAW_Y_TOP", "3880"))
LEGACY_RAW_Y_BOTTOM = int(os.environ.get("TOUCH_RAW_Y_BOTTOM", "360"))


@dataclass(frozen=True)
class Calibration:
    device: str
    swap_axes: bool
    raw_x_min: int
    raw_x_max: int
    raw_y_min: int
    raw_y_max: int


def _parse_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def applies_to(device_path: str) -> bool:
    return Path(device_path).name == Path(TOUCH_DEVICE).name


def load(device_path: str | None = None) -> Calibration:
    device = device_path or TOUCH_DEVICE
    return Calibration(
        device=device,
        swap_axes=_parse_bool(os.environ.get("TOUCH_SWAP_AXES"), True),
        raw_x_min=int(os.environ.get("TOUCH_RAW_X_MIN", str(LEGACY_RAW_X_LEFT))),
        raw_x_max=int(os.environ.get("TOUCH_RAW_X_MAX", str(LEGACY_RAW_X_RIGHT))),
        raw_y_min=int(os.environ.get("TOUCH_RAW_Y_MIN", str(LEGACY_RAW_Y_TOP))),
        raw_y_max=int(os.environ.get("TOUCH_RAW_Y_MAX", str(LEGACY_RAW_Y_BOTTOM))),
    )


def _scale(value: int, raw_min: int, raw_max: int, size: int) -> int:
    if size <= 1 or raw_min == raw_max:
        return 0
    pixel = round((value - raw_min) * (size - 1) / (raw_max - raw_min))
    return max(0, min(size - 1, pixel))


def map_to_screen(raw_x: int, raw_y: int, *, width: int, height: int, calibration: Calibration | None = None) -> tuple[int, int]:
    active = calibration or load()
    source_x = raw_y if active.swap_axes else raw_x
    source_y = raw_x if active.swap_axes else raw_y
    screen_x = _scale(source_x, active.raw_x_min, active.raw_x_max, width)
    screen_y = _scale(source_y, active.raw_y_min, active.raw_y_max, height)
    return screen_x, screen_y


def infer_from_corner_taps(device_path: str, taps: dict[str, tuple[int, int]]) -> Calibration:
    top_left = taps["top_left"]
    top_right = taps["top_right"]
    bottom_left = taps["bottom_left"]
    bottom_right = taps["bottom_right"]

    no_swap_score = abs(((top_right[0] + bottom_right[0]) / 2) - ((top_left[0] + bottom_left[0]) / 2)) + abs(
        ((bottom_left[1] + bottom_right[1]) / 2) - ((top_left[1] + top_right[1]) / 2)
    )
    swap_score = abs(((top_right[1] + bottom_right[1]) / 2) - ((top_left[1] + bottom_left[1]) / 2)) + abs(
        ((bottom_left[0] + bottom_right[0]) / 2) - ((top_left[0] + top_right[0]) / 2)
    )

    if swap_score >= no_swap_score:
        raw_x_min = round((top_left[1] + bottom_left[1]) / 2)
        raw_x_max = round((top_right[1] + bottom_right[1]) / 2)
        raw_y_min = round((top_left[0] + top_right[0]) / 2)
        raw_y_max = round((bottom_left[0] + bottom_right[0]) / 2)
        return Calibration(device=device_path, swap_axes=True, raw_x_min=raw_x_min, raw_x_max=raw_x_max, raw_y_min=raw_y_min, raw_y_max=raw_y_max)

    raw_x_min = round((top_left[0] + bottom_left[0]) / 2)
    raw_x_max = round((top_right[0] + bottom_right[0]) / 2)
    raw_y_min = round((top_left[1] + top_right[1]) / 2)
    raw_y_max = round((bottom_left[1] + bottom_right[1]) / 2)
    return Calibration(device=device_path, swap_axes=False, raw_x_min=raw_x_min, raw_x_max=raw_x_max, raw_y_min=raw_y_min, raw_y_max=raw_y_max)


def format_exports(calibration: Calibration) -> list[str]:
    return [
        f"TOUCH_DEVICE={calibration.device}",
        f"TOUCH_SWAP_AXES={'1' if calibration.swap_axes else '0'}",
        f"TOUCH_RAW_X_MIN={calibration.raw_x_min}",
        f"TOUCH_RAW_X_MAX={calibration.raw_x_max}",
        f"TOUCH_RAW_Y_MIN={calibration.raw_y_min}",
        f"TOUCH_RAW_Y_MAX={calibration.raw_y_max}",
    ]
