#!/usr/bin/env python3
"""Framebuffer video player for credits and vault flows."""

from __future__ import annotations

import argparse
import os
import select
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PIL import Image, ImageDraw, ImageFont

from boot.boot_selector import (
    DEFAULT_THEME_ID,
    DEFAULT_THEME_ROOT,
    DEFAULT_THEME_STATE_PATH,
    ThemeStateStore,
    load_theme_catalog,
    load_theme_selection,
    validate_theme_selection,
    write_framebuffer_image,
)
from framebuffer import FramebufferWriter
from rotator.touch import (
    ABS_MT_POSITION_X,
    ABS_MT_POSITION_Y,
    ABS_MT_TRACKING_ID,
    ABS_X,
    ABS_Y,
    BTN_TOUCH,
    EV_ABS,
    EV_KEY,
    EV_SYN,
    INPUT_EVENT_STRUCT,
    detect_touch_width,
    touch_probe,
)
import touch_calibration


WIDTH = 320
HEIGHT = 240
FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
PLAYER_MODE_ENV = "ZERO2DASH_PLAYER_MODE"
PLAYER_MODE_CREDITS = "credits"
PLAYER_MODE_VAULT = "vault"
THEME_ROOT_DEFAULT = Path(os.environ.get("BOOT_SELECTOR_THEME_ROOT", str(DEFAULT_THEME_ROOT)))
THEME_STATE_PATH_DEFAULT = Path(os.environ.get("BOOT_SELECTOR_THEME_STATE_PATH", str(DEFAULT_THEME_STATE_PATH)))
VAULT_BACKGROUND_PATH = BASE_DIR / "themes" / "global_images" / "vault.png"
TOUCH_SETTLE_SECS = float(os.environ.get("ZERO2DASH_PLAYER_TOUCH_SETTLE_SECS", "0.20"))
STARTUP_TOUCH_IDLE_SECS = 0.20
STARTUP_TOUCH_MAX_WAIT_SECS = 1.50
SCROLL_HOLD_DELAY_SECS = 0.5
SCROLL_REPEAT_SECS = 1.0 / 3.0
HOLD_TO_EXIT_SECS = 2.0
LEFT_DOUBLE_TAP_WINDOW_SECS = 1.0
OVERLAY_DELAY_SECS = 3.0
OVERLAY_SHOW_SECS = 3.0
OVERLAY_FADE_SECS = 0.18
OVERLAY_FRAME_STEP_SECS = 0.05
SYNTHETIC_TOUCH_TIMEOUT_SECS = 0.35
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi"}
FFMPEG_FILTER = "fps=15,crop=320:240:(in_w-320)/2:0,format=rgb565le"
CREDITS_DIR_ENV = "ZERO2DASH_PLAYER_CREDITS_DIR"
VAULT_DIR_ENV = "ZERO2DASH_PLAYER_VAULT_DIR"

# Player UI layout. Adjust here if text or touch regions need tuning later.
ROW_X = 40
ROW_Y = 46
ROW_WIDTH = 230
ROW_HEIGHT = 40
VISIBLE_ROWS = 3
SCROLL_STRIP_X = ROW_X + ROW_WIDTH
SCROLL_STRIP_Y = ROW_Y
SCROLL_STRIP_WIDTH = 20
SCROLL_STRIP_HEIGHT = ROW_HEIGHT * VISIBLE_ROWS
PLAY_BUTTON_X = 72
PLAY_BUTTON_Y = 198
PLAY_BUTTON_WIDTH = 175
PLAY_BUTTON_HEIGHT = 25
BACK_STRIP_X = WIDTH - 20
BACK_STRIP_WIDTH = 20
LIST_TEXT_X = ROW_X + 12
LIST_TEXT_WIDTH = ROW_WIDTH - 24
HIGHLIGHT_X = ROW_X - 10
HIGHLIGHT_WIDTH = ROW_WIDTH
ROW_TEXT_FONT_SIZE = 21
TEXT_FILL = (0, 11, 61)
TEXT_SUBTLE_FILL = (0, 11, 61)
SELECTED_TEXT_FILL = (255, 255, 255)
HIGHLIGHT_FILL = (2, 12, 69, 230)
HIGHLIGHT_OUTLINE = (2, 12, 69, 255)
NO_FILES_LABEL = "NO FILES"
STOP_REQUESTED = False
FONT_CANDIDATES = (
    "cour.ttf",
    "Courier New.ttf",
    "DejaVuSansMono.ttf",
    "LiberationMono-Regular.ttf",
    "DejaVuSans.ttf",
)


def request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


@dataclass(frozen=True)
class PlayerAssets:
    theme_id: str
    background: Image.Image
    overlay: Image.Image


@dataclass(frozen=True)
class TouchSample:
    x: int
    y: int
    is_down: bool
    just_pressed: bool
    just_released: bool
    now: float


@dataclass
class PlaylistState:
    files: list[Path]
    selected_index: int = 0
    top_index: int = 0
    current_index: int | None = None

    def has_files(self) -> bool:
        return bool(self.files)

    def max_top_index(self) -> int:
        return max(0, len(self.files) - VISIBLE_ROWS)

    def scroll(self, delta: int) -> bool:
        new_top = max(0, min(self.max_top_index(), self.top_index + delta))
        if new_top == self.top_index:
            return False
        self.top_index = new_top
        return True

    def visible_rows(self) -> list[tuple[int, Path]]:
        rows: list[tuple[int, Path]] = []
        for row in range(VISIBLE_ROWS):
            index = self.top_index + row
            if index >= len(self.files):
                break
            rows.append((index, self.files[index]))
        return rows

    def select_visible_row(self, row: int) -> bool:
        index = self.top_index + row
        if row < 0 or row >= VISIBLE_ROWS or index >= len(self.files):
            return False
        self.selected_index = index
        return True

    def start_from_selection(self) -> int | None:
        if not self.files:
            self.current_index = None
            return None
        self.current_index = max(0, min(self.selected_index, len(self.files) - 1))
        return self.current_index

    def current_file(self) -> Path | None:
        if self.current_index is None or not self.files:
            return None
        return self.files[self.current_index]

    def advance(self, delta: int) -> int | None:
        if not self.files:
            self.current_index = None
            return None
        current = self.current_index if self.current_index is not None else self.start_from_selection()
        assert current is not None
        self.current_index = (current + delta) % len(self.files)
        return self.current_index


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def ellipsise(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    suffix = "..."
    suffix_width = draw.textlength(suffix, font=font)
    if suffix_width >= max_width:
        return suffix
    trimmed = text
    while trimmed and draw.textlength(trimmed, font=font) + suffix_width > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed}{suffix}"


def list_supported_videos(video_dir: Path) -> list[Path]:
    if not video_dir.is_dir():
        return []
    files = [path for path in video_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_SUFFIXES]
    files.sort(key=lambda path: path.name.casefold())
    return files


def resolve_mode() -> str:
    mode = os.environ.get(PLAYER_MODE_ENV, PLAYER_MODE_CREDITS).strip().lower()
    if mode not in {PLAYER_MODE_CREDITS, PLAYER_MODE_VAULT}:
        return PLAYER_MODE_CREDITS
    return mode


def resolve_video_dir(mode: str) -> Path:
    subdir = "x" if mode == PLAYER_MODE_VAULT else "vid"
    override_env = VAULT_DIR_ENV if mode == PLAYER_MODE_VAULT else CREDITS_DIR_ENV
    override = os.environ.get(override_env, "").strip()
    if override:
        return Path(override).expanduser()

    candidates: list[Path] = []
    home_env = os.environ.get("HOME", "").strip()
    if home_env:
        candidates.append(Path(home_env) / subdir)
    candidates.append(Path.home() / subdir)
    candidates.append(Path("/home/pihole") / subdir)

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_dir():
            return candidate
    return candidates[0]


def load_assets(mode: str) -> PlayerAssets:
    theme_catalog = load_theme_catalog(THEME_ROOT_DEFAULT)
    theme_id = validate_theme_selection(
        load_theme_selection(ThemeStateStore(THEME_STATE_PATH_DEFAULT), theme_catalog, DEFAULT_THEME_ID),
        theme_catalog,
    )
    theme_assets = theme_catalog[theme_id]
    background_path = theme_assets.root / "player.png"
    if mode == PLAYER_MODE_VAULT:
        background_path = VAULT_BACKGROUND_PATH
        if not background_path.exists():
            raise FileNotFoundError(f"Vault background is missing: {background_path}")
    overlay_path = theme_assets.root / "overlay.png"
    return PlayerAssets(
        theme_id=theme_id,
        background=Image.open(background_path).convert("RGBA").resize((WIDTH, HEIGHT)),
        overlay=Image.open(overlay_path).convert("RGBA").resize((WIDTH, HEIGHT)),
    )


class TouchInput:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.device, self.reason = touch_probe()
        self._fd = None
        self._touch_width = width
        self._touch_min_x = 0
        self._use_calibration = bool(self.device and touch_calibration.applies_to(self.device))
        if self.device and not self._use_calibration:
            self._touch_width, self._touch_min_x = detect_touch_width(self.device, width)
        self._last_x = width // 2
        self._last_y = height // 2
        self._touch_down = False
        self._saw_explicit_touch_state = False
        self._pending_abs_sample = False
        self._last_synthetic_sample_at = 0.0

    def is_available(self) -> bool:
        return self.device is not None

    def is_touch_active(self) -> bool:
        return self._touch_down

    def close(self) -> None:
        if self._fd is not None:
            try:
                self._fd.close()
            finally:
                self._fd = None

    def _ensure_open(self):
        if self.device is None:
            return None
        if self._fd is None:
            self._fd = open(self.device, "rb", buffering=0)
        return self._fd

    def _map_coordinates(self, raw_x: int, raw_y: int) -> tuple[int, int]:
        if self._use_calibration:
            return touch_calibration.map_to_screen(raw_x, raw_y, width=self.width, height=self.height)
        relative_x = raw_x - self._touch_min_x
        if relative_x < 0:
            relative_x = 0
        elif relative_x >= self._touch_width:
            relative_x = self._touch_width - 1
        return min(self.width - 1, max(0, relative_x)), min(self.height - 1, max(0, raw_y))

    def poll(self, timeout_secs: float) -> TouchSample | None:
        fd = self._ensure_open()
        if fd is None:
            time.sleep(timeout_secs)
            return None
        readable, _, _ = select.select([fd], [], [], timeout_secs)
        now = time.monotonic()
        if not readable:
            if self._touch_down and not self._saw_explicit_touch_state and self._last_synthetic_sample_at:
                if (now - self._last_synthetic_sample_at) >= SYNTHETIC_TOUCH_TIMEOUT_SECS:
                    self._touch_down = False
                    x, y = self._map_coordinates(self._last_x, self._last_y)
                    return TouchSample(x, y, False, False, True, now)
            return None

        raw = fd.read(INPUT_EVENT_STRUCT.size)
        if len(raw) != INPUT_EVENT_STRUCT.size:
            return None
        _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)

        if ev_type == EV_ABS and ev_code in (ABS_X, ABS_MT_POSITION_X):
            self._last_x = ev_value
            self._pending_abs_sample = True
            if self._touch_down:
                x, y = self._map_coordinates(self._last_x, self._last_y)
                return TouchSample(x, y, True, False, False, now)
            return None

        if ev_type == EV_ABS and ev_code in (ABS_Y, ABS_MT_POSITION_Y):
            self._last_y = ev_value
            self._pending_abs_sample = True
            if self._touch_down:
                x, y = self._map_coordinates(self._last_x, self._last_y)
                return TouchSample(x, y, True, False, False, now)
            return None

        if ev_type == EV_KEY and ev_code == BTN_TOUCH:
            self._saw_explicit_touch_state = True
            x, y = self._map_coordinates(self._last_x, self._last_y)
            if ev_value == 1:
                self._touch_down = True
                return TouchSample(x, y, True, True, False, now)
            if ev_value == 0 and self._touch_down:
                self._touch_down = False
                return TouchSample(x, y, False, False, True, now)
            return None

        if ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
            self._saw_explicit_touch_state = True
            x, y = self._map_coordinates(self._last_x, self._last_y)
            if ev_value >= 0:
                self._touch_down = True
                return TouchSample(x, y, True, True, False, now)
            if self._touch_down:
                self._touch_down = False
                return TouchSample(x, y, False, False, True, now)
            return None

        if ev_type == EV_SYN and self._pending_abs_sample and not self._saw_explicit_touch_state:
            self._pending_abs_sample = False
            self._last_synthetic_sample_at = now
            x, y = self._map_coordinates(self._last_x, self._last_y)
            if not self._touch_down:
                self._touch_down = True
                return TouchSample(x, y, True, True, False, now)
            return TouchSample(x, y, True, False, False, now)

        return None


class FfmpegPlayback:
    def __init__(self, fbdev: str) -> None:
        self.fbdev = fbdev
        self.process: subprocess.Popen[str] | None = None
        self.paused = False

    def _command_for_video(self, video: Path) -> list[str]:
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-stats",
            "-re",
            "-threads",
            "2",
            "-i",
            str(video),
            "-vf",
            FFMPEG_FILTER,
            "-an",
            "-sn",
            "-dn",
            "-f",
            "fbdev",
            self.fbdev,
        ]

    def start(self, video: Path) -> None:
        self.stop()
        self.process = subprocess.Popen(self._command_for_video(video), text=True)
        self.paused = False

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2.0)
        self.process = None
        self.paused = False

    def toggle_pause(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        if self.paused:
            os.kill(self.process.pid, signal.SIGCONT)
        else:
            os.kill(self.process.pid, signal.SIGSTOP)
        self.paused = not self.paused

    def poll(self) -> int | None:
        if self.process is None:
            return None
        return self.process.poll()


def overlay_alpha(elapsed_secs: float) -> int:
    if elapsed_secs <= 0.0 or elapsed_secs >= OVERLAY_SHOW_SECS:
        return 0
    fade_window = min(OVERLAY_FADE_SECS, OVERLAY_SHOW_SECS / 2.0)
    if fade_window <= 0.0:
        return 255
    if elapsed_secs < fade_window:
        return max(0, min(255, round((elapsed_secs / fade_window) * 255)))
    fade_out_start = OVERLAY_SHOW_SECS - fade_window
    if elapsed_secs > fade_out_start:
        return max(0, min(255, round(((OVERLAY_SHOW_SECS - elapsed_secs) / fade_window) * 255)))
    return 255


def wait_until(deadline: float) -> None:
    while not STOP_REQUESTED and time.monotonic() < deadline:
        time.sleep(OVERLAY_FRAME_STEP_SECS)


def render_selection_screen(framebuffer: FramebufferWriter, assets: PlayerAssets, state: PlaylistState) -> None:
    image = assets.background.copy()
    draw = ImageDraw.Draw(image, "RGBA")
    row_font = load_font(ROW_TEXT_FONT_SIZE)

    if not state.files:
        row = 1
        label = ellipsise(draw, NO_FILES_LABEL, row_font, LIST_TEXT_WIDTH)
        label_bbox = draw.textbbox((0, 0), label, font=row_font)
        label_h = label_bbox[3] - label_bbox[1]
        label_y = ROW_Y + (row * ROW_HEIGHT) + max(0, (ROW_HEIGHT - label_h) // 2)
        draw.text((LIST_TEXT_X, label_y), label, font=row_font, fill=TEXT_SUBTLE_FILL)
        write_framebuffer_image(framebuffer, image.convert("RGB"))
        return

    visible = dict(state.visible_rows())
    for row in range(VISIBLE_ROWS):
        index = state.top_index + row
        if index >= len(state.files):
            continue
        top = ROW_Y + (row * ROW_HEIGHT)
        bottom = top + ROW_HEIGHT - 1
        if index == state.selected_index:
            draw.rounded_rectangle(
                (HIGHLIGHT_X, top, HIGHLIGHT_X + HIGHLIGHT_WIDTH - 1, bottom),
                radius=10,
                fill=HIGHLIGHT_FILL,
                outline=HIGHLIGHT_OUTLINE,
                width=2,
            )
        label = ellipsise(draw, visible[index].name, row_font, LIST_TEXT_WIDTH)
        bbox = draw.textbbox((0, 0), label, font=row_font)
        label_h = bbox[3] - bbox[1]
        label_y = top + max(0, (ROW_HEIGHT - label_h) // 2)
        fill = SELECTED_TEXT_FILL if index == state.selected_index else TEXT_FILL
        draw.text((LIST_TEXT_X, label_y), label, font=row_font, fill=fill)

    write_framebuffer_image(framebuffer, image.convert("RGB"))


def show_overlay(framebuffer: FramebufferWriter, assets: PlayerAssets, playback: FfmpegPlayback | None = None) -> None:
    wait_until(time.monotonic() + OVERLAY_DELAY_SECS)
    if STOP_REQUESTED:
        return

    resume_after_overlay = False
    if playback is not None and playback.process is not None and playback.poll() is None and not playback.paused:
        playback.toggle_pause()
        resume_after_overlay = True

    started_at = time.monotonic()
    while not STOP_REQUESTED:
        elapsed = time.monotonic() - started_at
        alpha = overlay_alpha(elapsed)
        if alpha <= 0:
            if elapsed >= OVERLAY_SHOW_SECS:
                return
            wait_until(time.monotonic() + OVERLAY_FRAME_STEP_SECS)
            continue
        base = assets.background.copy()
        overlay = assets.overlay.copy()
        overlay.putalpha(alpha)
        composite = Image.alpha_composite(base, overlay)
        write_framebuffer_image(framebuffer, composite.convert("RGB"))
        wait_until(time.monotonic() + OVERLAY_FRAME_STEP_SECS)

    if resume_after_overlay and playback is not None and playback.process is not None and playback.poll() is None and playback.paused:
        playback.toggle_pause()


def run_pre_play_hook() -> None:
    hook = Path("/usr/local/bin/pihole-display-pre.sh")
    if hook.exists() and os.access(hook, os.X_OK):
        try:
            subprocess.run([str(hook)], check=False)
        except OSError:
            pass


def in_back_strip(x: int) -> bool:
    return x >= BACK_STRIP_X


def in_play_button(x: int, y: int) -> bool:
    return PLAY_BUTTON_X <= x < (PLAY_BUTTON_X + PLAY_BUTTON_WIDTH) and PLAY_BUTTON_Y <= y < (PLAY_BUTTON_Y + PLAY_BUTTON_HEIGHT)


def scroll_direction_for_point(x: int, y: int) -> int | None:
    if not (SCROLL_STRIP_X <= x < (SCROLL_STRIP_X + SCROLL_STRIP_WIDTH)):
        return None
    if not (SCROLL_STRIP_Y <= y < (SCROLL_STRIP_Y + SCROLL_STRIP_HEIGHT)):
        return None
    midpoint = SCROLL_STRIP_Y + (SCROLL_STRIP_HEIGHT // 2)
    return -1 if y < midpoint else 1


def row_for_point(x: int, y: int, state: PlaylistState) -> int | None:
    if not (ROW_X <= x < (ROW_X + ROW_WIDTH)):
        return None
    if not (ROW_Y <= y < (ROW_Y + (ROW_HEIGHT * VISIBLE_ROWS))):
        return None
    row = (y - ROW_Y) // ROW_HEIGHT
    if state.top_index + row >= len(state.files):
        return None
    return row


def playback_zone(x: int) -> str:
    if x < WIDTH // 3:
        return "left"
    if x < (2 * WIDTH) // 3:
        return "center"
    return "right"


def wait_for_touch_idle(
    touch_input: TouchInput,
    idle_secs: float = STARTUP_TOUCH_IDLE_SECS,
    max_wait_secs: float = STARTUP_TOUCH_MAX_WAIT_SECS,
) -> None:
    """Discard inherited shell touch events before the player becomes interactive."""
    started_at = time.monotonic()
    idle_started_at: float | None = None
    while not STOP_REQUESTED and (time.monotonic() - started_at) < max_wait_secs:
        sample = touch_input.poll(0.05)
        now = time.monotonic()
        if sample is not None or touch_input.is_touch_active():
            idle_started_at = None
            continue
        if idle_started_at is None:
            idle_started_at = now
            continue
        if (now - idle_started_at) >= idle_secs:
            return


def run_selection_mode(framebuffer: FramebufferWriter, assets: PlayerAssets, state: PlaylistState, touch_input: TouchInput) -> bool:
    render_selection_screen(framebuffer, assets, state)
    wait_for_touch_idle(touch_input)
    down_at = None
    scroll_direction = None
    repeated_scroll = False
    next_repeat_at = None
    touch_active = False
    settle_until = time.monotonic() + TOUCH_SETTLE_SECS
    while not STOP_REQUESTED:
        sample = touch_input.poll(0.05)
        now = time.monotonic()
        if sample is not None and now < settle_until:
            continue
        if touch_active and scroll_direction is not None and down_at is not None and next_repeat_at is not None and now >= next_repeat_at:
            if state.scroll(scroll_direction):
                render_selection_screen(framebuffer, assets, state)
            repeated_scroll = True
            next_repeat_at = now + SCROLL_REPEAT_SECS
        if sample and sample.just_pressed:
            touch_active = True
            down_at = sample.now
            scroll_direction = scroll_direction_for_point(sample.x, sample.y)
            repeated_scroll = False
            next_repeat_at = sample.now + SCROLL_HOLD_DELAY_SECS if scroll_direction is not None else None
        elif sample and sample.just_released:
            touch_active = False
            if in_back_strip(sample.x):
                return False
            if scroll_direction is not None and down_at is not None:
                held_for = sample.now - down_at
                if held_for < SCROLL_HOLD_DELAY_SECS and not repeated_scroll and state.scroll(scroll_direction):
                    render_selection_screen(framebuffer, assets, state)
                down_at = None
                scroll_direction = None
                repeated_scroll = False
                next_repeat_at = None
                continue
            if in_play_button(sample.x, sample.y) and state.has_files():
                state.start_from_selection()
                return True
            row = row_for_point(sample.x, sample.y, state)
            if row is not None and state.select_visible_row(row):
                render_selection_screen(framebuffer, assets, state)
            down_at = None
            scroll_direction = None
            repeated_scroll = False
            next_repeat_at = None
    return False


def run_playback_mode(framebuffer: FramebufferWriter, assets: PlayerAssets, state: PlaylistState, touch_input: TouchInput, fbdev: str) -> None:
    if state.current_index is None:
        return
    playback = FfmpegPlayback(fbdev)
    try:
        playback.start(state.current_file())
        show_overlay(framebuffer, assets, playback)
        left_tap_at = 0.0
        touch_started_at = 0.0
        touch_active = False
        exit_triggered = False
        while not STOP_REQUESTED and not exit_triggered:
            sample = touch_input.poll(0.05)
            now = time.monotonic()
            if touch_active and (now - touch_started_at) >= HOLD_TO_EXIT_SECS:
                exit_triggered = True
                continue
            if sample and sample.just_pressed:
                touch_active = True
                touch_started_at = sample.now
            elif sample and sample.just_released:
                touch_active = False
                if in_back_strip(sample.x):
                    exit_triggered = True
                    continue
                zone = playback_zone(sample.x)
                if zone == "left":
                    if (sample.now - left_tap_at) <= LEFT_DOUBLE_TAP_WINDOW_SECS:
                        state.advance(-1)
                        playback.start(state.current_file())
                        left_tap_at = 0.0
                    else:
                        playback.start(state.current_file())
                        left_tap_at = sample.now
                elif zone == "center":
                    playback.toggle_pause()
                else:
                    state.advance(1)
                    playback.start(state.current_file())

            return_code = playback.poll()
            if return_code is not None:
                if exit_triggered or STOP_REQUESTED:
                    break
                state.advance(1)
                playback.start(state.current_file())
        playback.stop()
    finally:
        render_selection_screen(framebuffer, assets, state)


def run_self_test() -> int:
    names = [Path("b.MKV"), Path("A.mp4"), Path("notes.txt"), Path("c.avi")]
    tmp_dir = Path(os.environ.get("TEMP", "/tmp")) / "zero2dash-player-self-test"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (tmp_dir / name.name).write_text("x", encoding="utf-8")
    try:
        files = list_supported_videos(tmp_dir)
        assert [path.name for path in files] == ["A.mp4", "b.MKV", "c.avi"]
        state = PlaylistState(files)
        assert state.scroll(1) is False
        assert state.select_visible_row(0) is True
        assert state.start_from_selection() == 0
        assert state.advance(1) == 1
        assert state.advance(1) == 2
        assert state.advance(1) == 0
        print("[player] self-test passed", flush=True)
        return 0
    finally:
        for path in tmp_dir.iterdir():
            path.unlink()
        tmp_dir.rmdir()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Framebuffer player for zero2dash credits and vault flows.")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device (default: {FBDEV_DEFAULT})")
    parser.add_argument("--self-test", action="store_true", help="Run lightweight logic checks and exit.")
    return parser.parse_args()


def validate_environment(mode: str, fbdev: str) -> None:
    if mode == PLAYER_MODE_VAULT and not VAULT_BACKGROUND_PATH.exists():
        raise FileNotFoundError(f"Vault background is missing: {VAULT_BACKGROUND_PATH}")
    if not Path(fbdev).exists():
        raise FileNotFoundError(f"Framebuffer device not found: {fbdev}")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required but not installed.")


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    mode = resolve_mode()
    try:
        validate_environment(mode, args.fbdev)
        assets = load_assets(mode)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[player] {exc}", file=sys.stderr, flush=True)
        return 1

    video_dir = resolve_video_dir(mode)
    state = PlaylistState(list_supported_videos(video_dir))
    print(f"[player] mode={mode} video_dir={video_dir} file_count={len(state.files)}", flush=True)
    touch_input = TouchInput(WIDTH, HEIGHT)
    if not touch_input.is_available():
        print(f"[player] No usable touch device found ({touch_input.reason}).", file=sys.stderr, flush=True)
        return 1

    framebuffer = FramebufferWriter(args.fbdev, WIDTH, HEIGHT)
    framebuffer.open()
    run_pre_play_hook()
    try:
        while not STOP_REQUESTED:
            should_play = run_selection_mode(framebuffer, assets, state, touch_input)
            if not should_play:
                return 0
            run_playback_mode(framebuffer, assets, state, touch_input, args.fbdev)
        return 0
    finally:
        touch_input.close()
        framebuffer.close()


if __name__ == "__main__":
    raise SystemExit(main())
