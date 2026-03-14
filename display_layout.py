"""Shared 320x240 text layout helpers for module display pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CanvasAlign = Literal["left", "right", "center"]

CANVAS_WIDTH = 320
CANVAS_HEIGHT = 240
HEADER_HEIGHT = 80
ROW_HEIGHT = 32
BODY_ROWS = 5
SIDE_MARGIN = 15
BODY_WIDTH = CANVAS_WIDTH - (SIDE_MARGIN * 2)


@dataclass(frozen=True)
class Column:
    left: int
    width: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def centre_x(self) -> int:
        return self.left + (self.width // 2)


@dataclass(frozen=True)
class Layout:
    left: Column
    right: Column

    @property
    def body(self) -> Column:
        return Column(SIDE_MARGIN, BODY_WIDTH)

    def row_top(self, row_index: int) -> int:
        return HEADER_HEIGHT + (row_index * ROW_HEIGHT)

    def row_centre_y(self, row_index: int) -> int:
        return self.row_top(row_index) + (ROW_HEIGHT // 2)


LAYOUT_2_1 = Layout(
    left=Column(SIDE_MARGIN, 200),
    right=Column(SIDE_MARGIN + 200, 100),
)

LAYOUT_HALF = Layout(
    left=Column(SIDE_MARGIN, 150),
    right=Column(SIDE_MARGIN + 150, 150),
)


def text_bbox(font, text: str) -> tuple[int, int, int, int]:
    return font.getbbox(text)


def text_width(font, text: str) -> int:
    bbox = text_bbox(font, text)
    return bbox[2] - bbox[0]


def centred_text_y(font, text: str, centre_y: int) -> int:
    top, bottom = text_bbox(font, text)[1], text_bbox(font, text)[3]
    return centre_y - ((top + bottom) // 2)


def aligned_text_x(column: Column, font, text: str, align: CanvasAlign) -> int:
    width = text_width(font, text)
    if align == "left":
        return column.left
    if align == "right":
        return column.right - width
    return column.centre_x - (width // 2)


def fit_font(text: str, *, width_limit: int, preferred_size: int, min_size: int, loader, **loader_kwargs):
    for size in range(preferred_size, min_size - 1, -1):
        font = loader(size, **loader_kwargs)
        if text_width(font, text) <= width_limit:
            return font
    return loader(min_size, **loader_kwargs)


def ellipsize_text(text: str, font, width_limit: int) -> str:
    if text_width(font, text) <= width_limit:
        return text

    ellipsis = "..."
    available = width_limit - text_width(font, ellipsis)
    if available <= 0:
        return ellipsis

    trimmed = text
    while trimmed and text_width(font, trimmed) > available:
        trimmed = trimmed[:-1].rstrip()
    return f"{trimmed}{ellipsis}" if trimmed else ellipsis


def truncate_pair(
    left_text: str,
    right_text: str,
    *,
    left_font,
    right_font,
    left_width_limit: int,
    right_width_limit: int,
) -> tuple[str, str]:
    truncated_right = ellipsize_text(right_text, right_font, right_width_limit)
    truncated_left = ellipsize_text(left_text, left_font, left_width_limit)
    return truncated_left, truncated_right
