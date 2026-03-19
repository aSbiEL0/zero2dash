from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LEFT_STRIP_WIDTH = 32
MENU_TOGGLE = "menu_toggle"
MENU_NASA = "nasa"
PAGE_ONE = 0
PAGE_TWO = 1

PAGE_ACTIONS = {
    PAGE_ONE: (("home", "info"), (MENU_NASA, "shutdown")),
    PAGE_TWO: (("home", "info"), ("padlock", "shutdown")),
}

PAGE_LABELS = {
    "home": ("Day/Night", (50, 109, 168)),
    "info": ("Info", (87, 96, 115)),
    MENU_NASA: ("NASA ISS", (235, 191, 62)),
    "shutdown": ("Shutdown", (155, 72, 72)),
    "padlock": ("Photos", (68, 122, 109)),
}


def _font(size: int, *, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/NotoSans-Bold.ttf" if bold else "C:/Windows/Fonts/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def menu_specs(page: int, width: int, height: int) -> list[tuple[str, int, int, int, int]]:
    content_left = LEFT_STRIP_WIDTH
    content_width = max(1, width - LEFT_STRIP_WIDTH)
    mid_x = content_left + (content_width // 2)
    mid_y = height // 2
    actions = PAGE_ACTIONS.get(page, PAGE_ACTIONS[PAGE_ONE])
    return [
        (MENU_TOGGLE, 0, 0, LEFT_STRIP_WIDTH - 1, height - 1),
        (actions[0][0], content_left, 0, max(content_left, mid_x - 1), max(0, mid_y - 1)),
        (actions[0][1], mid_x, 0, width - 1, max(0, mid_y - 1)),
        (actions[1][0], content_left, mid_y, max(content_left, mid_x - 1), height - 1),
        (actions[1][1], mid_x, mid_y, width - 1, height - 1),
    ]


def _wrap(text: str) -> str:
    return text.replace(" ", "\n") if len(text) > 8 else text


def render_menu_page(page: int, width: int, height: int, image_path: str | None = None) -> Image.Image:
    target = Path(image_path) if image_path else None
    if target and target.exists():
        with Image.open(target) as source:
            return source.convert("RGB").resize((width, height))

    image = Image.new("RGB", (width, height), (10, 14, 24))
    draw = ImageDraw.Draw(image)
    title_font = _font(16, bold=True)
    tile_font = _font(18, bold=True)
    badge_font = _font(11, bold=False)

    draw.rectangle((0, 0, LEFT_STRIP_WIDTH - 1, height - 1), fill=(26, 30, 44))
    draw.text((8, 14), "P\nA\nG\nE\nS", font=badge_font, fill=(228, 232, 242), spacing=1)
    draw.rounded_rectangle((4, height - 30, LEFT_STRIP_WIDTH - 5, height - 6), radius=8, fill=(48, 56, 80))
    draw.text((10, height - 25), f"{page + 1}", font=title_font, fill=(255, 255, 255))

    for action, left, top, right, bottom in menu_specs(page, width, height)[1:]:
        label, colour = PAGE_LABELS[action]
        draw.rounded_rectangle((left + 6, top + 6, right - 6, bottom - 6), radius=18, fill=colour)
        text = _wrap(label)
        bbox = tile_font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = left + ((right - left - text_width) // 2)
        text_y = top + ((bottom - top - text_height) // 2)
        fill = (20, 16, 10) if action == MENU_NASA else (248, 248, 248)
        draw.multiline_text((text_x, text_y), text, font=tile_font, fill=fill, align="center", spacing=2)
    return image
