#!/usr/bin/env python3
"""Boot-time framebuffer selector for day and night display modes."""

from __future__ import annotations

import argparse
import fcntl
import glob
import mmap
import os
import re
import select
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageSequence


FBDEV_DEFAULT = os.environ.get("FB_DEVICE", "/dev/fb1")
WIDTH_DEFAULT = int(os.environ.get("FB_WIDTH", "320"))
HEIGHT_DEFAULT = int(os.environ.get("FB_HEIGHT", "240"))
DEFAULT_GIF_PATH = os.environ.get("BOOT_SELECTOR_GIF_PATH", "boot/startup.gif")
DEFAULT_SELECTOR_IMAGE_PATH = os.environ.get("BOOT_SELECTOR_IMAGE_PATH", "boot/selector.png")
DEFAULT_DAY_SERVICE = os.environ.get("BOOT_SELECTOR_DAY_SERVICE", "display.service")
DEFAULT_NIGHT_SERVICE = os.environ.get("BOOT_SELECTOR_NIGHT_SERVICE", "night.service")
DEFAULT_TOUCH_SETTLE_SECS = float(os.environ.get("BOOT_SELECTOR_TOUCH_SETTLE_SECS", "0.35"))
DEFAULT_TOUCH_DEBOUNCE_SECS = float(os.environ.get("BOOT_SELECTOR_TOUCH_DEBOUNCE_SECS", "0.35"))
DEFAULT_GIF_SPEED = float(os.environ.get("BOOT_SELECTOR_GIF_SPEED", "0.5"))
DEFAULT_TOUCH_INVERT_Y = os.environ.get("BOOT_SELECTOR_TOUCH_INVERT_Y", "1").strip().lower() not in {"0", "false", "no", "off"}
DEFAULT_GIF_FRAME_MS = 100
BACKGROUND_RGB = (0, 0, 0)
RESAMPLING_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
STOP_REQUESTED = False
BASE_DIR = Path(__file__).resolve().parent.parent
DIRECT_MODE_COMMANDS = {
    "display.service": [sys.executable, "-u", str(BASE_DIR / "display_rotator.py")],
    "night.service": [sys.executable, "-u", str(BASE_DIR / "modules" / "blackout" / "blackout.py")],
}

# linux/input-event-codes.h
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03
ABS_X = 0x00
ABS_Y = 0x01
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39
BTN_TOUCH = 0x14A
INPUT_EVENT_STRUCT = struct.Struct("llHHI")
INPUT_ABSINFO_STRUCT = struct.Struct("iiiiii")

# linux/input.h EVIOCGABS(abs)
IOC_NRBITS = 8
IOC_TYPEBITS = 8
IOC_SIZEBITS = 14
IOC_DIRBITS = 2
IOC_NRSHIFT = 0
IOC_TYPESHIFT = IOC_NRSHIFT + IOC_NRBITS
IOC_SIZESHIFT = IOC_TYPESHIFT + IOC_TYPEBITS
IOC_DIRSHIFT = IOC_SIZESHIFT + IOC_SIZEBITS
IOC_READ = 2


def request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def _ioc(direction: int, ioc_type: int, number: int, size: int) -> int:
    return (direction << IOC_DIRSHIFT) | (ioc_type << IOC_TYPESHIFT) | (number << IOC_NRSHIFT) | (size << IOC_SIZESHIFT)


def eviocgabs(axis: int) -> int:
    return _ioc(IOC_READ, ord("E"), 0x40 + axis, INPUT_ABSINFO_STRUCT.size)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play a boot GIF once, then show a touch selector for day/night mode.")
    parser.add_argument("--fbdev", default=FBDEV_DEFAULT, help=f"Framebuffer device path (default: {FBDEV_DEFAULT})")
    parser.add_argument("--width", type=int, default=WIDTH_DEFAULT, help=f"Framebuffer width (default: {WIDTH_DEFAULT})")
    parser.add_argument("--height", type=int, default=HEIGHT_DEFAULT, help=f"Framebuffer height (default: {HEIGHT_DEFAULT})")
    parser.add_argument("--gif", default=DEFAULT_GIF_PATH, help=f"Startup GIF path (default: {DEFAULT_GIF_PATH})")
    parser.add_argument("--selector-image", default=DEFAULT_SELECTOR_IMAGE_PATH, help=f"Selector image path (default: {DEFAULT_SELECTOR_IMAGE_PATH})")
    parser.add_argument("--gif-speed", type=float, default=DEFAULT_GIF_SPEED, help=f"GIF playback speed multiplier (default: {DEFAULT_GIF_SPEED})")
    parser.add_argument("--invert-y", action="store_true", default=DEFAULT_TOUCH_INVERT_Y, help="Invert the touch Y axis when deciding top/bottom selection.")
    parser.add_argument("--no-invert-y", action="store_false", dest="invert_y", help="Disable Y-axis inversion for top/bottom selection.")
    parser.add_argument("--output-selector", help="Optional output path for the rendered selector screen.")
    parser.add_argument("--output-gif-first", help="Optional output path for the first rendered GIF frame.")
    parser.add_argument("--output-gif-last", help="Optional output path for the last rendered GIF frame.")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer writes for local verification.")
    parser.add_argument("--skip-gif", action="store_true", help="Skip GIF playback and show the selector immediately.")
    parser.add_argument("--probe-touch", action="store_true", help="Probe touch device selection and exit.")
    parser.add_argument(
        "--touch-settle-secs",
        type=float,
        default=DEFAULT_TOUCH_SETTLE_SECS,
        help=f"Ignore touches briefly after showing the selector (default: {DEFAULT_TOUCH_SETTLE_SECS})",
    )
    parser.add_argument(
        "--touch-debounce-secs",
        type=float,
        default=DEFAULT_TOUCH_DEBOUNCE_SECS,
        help=f"Minimum interval between accepted taps (default: {DEFAULT_TOUCH_DEBOUNCE_SECS})",
    )
    parser.add_argument("--day-service", default=DEFAULT_DAY_SERVICE, help=f"systemd unit to start for day mode (default: {DEFAULT_DAY_SERVICE})")
    parser.add_argument(
        "--night-service",
        default=DEFAULT_NIGHT_SERVICE,
        help=f"systemd unit to start for night mode (default: {DEFAULT_NIGHT_SERVICE})",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> int | None:
    if args.width <= 0 or args.height <= 0:
        print("Width/height must be positive integers.", file=sys.stderr)
        return 1
    if args.touch_settle_secs < 0 or args.touch_debounce_secs < 0:
        print("Touch timing values cannot be negative.", file=sys.stderr)
        return 1
    if args.gif_speed <= 0:
        print("GIF speed must be greater than zero.", file=sys.stderr)
        return 1
    return None


def rgb888_to_rgb565(image: Image.Image) -> bytes:
    r, g, b = image.split()
    r = r.point(lambda value: value >> 3)
    g = g.point(lambda value: value >> 2)
    b = b.point(lambda value: value >> 3)

    rgb565 = bytearray()
    rp, gp, bp = r.tobytes(), g.tobytes(), b.tobytes()
    for idx in range(len(rp)):
        value = ((rp[idx] & 0x1F) << 11) | ((gp[idx] & 0x3F) << 5) | (bp[idx] & 0x1F)
        rgb565 += struct.pack("<H", value)
    return bytes(rgb565)


class FramebufferWriter:
    def __init__(self, fbdev: str, width: int, height: int) -> None:
        self.fbdev = fbdev
        self.expected = width * height * 2
        self._handle = None
        self._mapping = None

    def open(self) -> None:
        handle = open(self.fbdev, "r+b", buffering=0)
        mapping = mmap.mmap(handle.fileno(), self.expected, mmap.MAP_SHARED, mmap.PROT_WRITE)
        self._handle = handle
        self._mapping = mapping

    def write_image(self, image: Image.Image) -> None:
        if self._mapping is None:
            raise RuntimeError("Framebuffer is not open")
        payload = rgb888_to_rgb565(image)
        if len(payload) != self.expected:
            raise RuntimeError(f"Framebuffer payload size mismatch: expected {self.expected} bytes, got {len(payload)} bytes")
        self._mapping.seek(0)
        self._mapping.write(payload)

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _read_sysfs_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _capability_mask(event_path: str, capability: str) -> int:
    raw = _read_sysfs_text(Path("/sys/class/input") / Path(event_path).name / "device" / "capabilities" / capability)
    if not raw:
        return 0
    try:
        return int(raw, 16)
    except ValueError:
        return 0


def _touch_candidate_details(event_path: str) -> tuple[tuple[int, int, int, int], str]:
    base = Path("/sys/class/input") / Path(event_path).name / "device"
    name = _read_sysfs_text(base / "name")
    name_lc = name.lower()
    abs_mask = _capability_mask(event_path, "abs")
    key_mask = _capability_mask(event_path, "key")

    has_abs_x = bool(abs_mask & (1 << ABS_X))
    has_abs_y = bool(abs_mask & (1 << ABS_Y))
    has_abs_mt_x = bool(abs_mask & (1 << ABS_MT_POSITION_X))
    has_abs_mt_y = bool(abs_mask & (1 << ABS_MT_POSITION_Y))
    has_touch_abs = (has_abs_x and has_abs_y) or (has_abs_mt_x and has_abs_mt_y)
    has_btn_touch = bool(key_mask & (1 << BTN_TOUCH))

    name_bonus = 0
    if "touchscreen" in name_lc:
        name_bonus = 5
    elif "touch" in name_lc:
        name_bonus = 3
    elif "mouse" in name_lc or "keyboard" in name_lc:
        name_bonus = -3

    score = (7 if has_touch_abs else -7) + (5 if has_btn_touch else -1) + name_bonus
    match = re.search(r"event(\d+)$", event_path)
    index = int(match.group(1)) if match else 999
    reason = (
        f"score={score}; name='{name or 'unknown'}'; "
        f"touch_abs={'yes' if has_touch_abs else 'no'} "
        f"(ABS_X={'yes' if has_abs_x else 'no'}, ABS_Y={'yes' if has_abs_y else 'no'}, "
        f"ABS_MT_POSITION_X={'yes' if has_abs_mt_x else 'no'}, ABS_MT_POSITION_Y={'yes' if has_abs_mt_y else 'no'}); "
        f"BTN_TOUCH={'yes' if has_btn_touch else 'no'}"
    )
    return (score, int(has_touch_abs), int(has_btn_touch), -index), reason


def _resolve_forced_touch_device() -> tuple[str | None, str | None]:
    forced = os.environ.get("TOUCH_DEVICE", "").strip() or os.environ.get("ROTATOR_TOUCH_DEVICE", "").strip()
    if not forced:
        return None, None

    resolved = forced
    if forced.startswith("event") and forced[5:].isdigit():
        resolved = f"/dev/input/{forced}"

    if Path(resolved).exists():
        source = "TOUCH_DEVICE" if os.environ.get("TOUCH_DEVICE", "").strip() else "ROTATOR_TOUCH_DEVICE"
        return resolved, f"forced by {source}={forced}"
    return None, f"configured override '{forced}' was not found"


def touch_probe() -> tuple[str | None, str]:
    forced_path, forced_reason = _resolve_forced_touch_device()
    if forced_reason and forced_path is not None:
        return forced_path, forced_reason

    candidates = sorted(glob.glob("/dev/input/event*"))
    if not candidates:
        return None, "no /dev/input/event* devices found"

    ranked: list[tuple[tuple[int, int, int, int], str, str]] = []
    for path in candidates:
        rank, reason = _touch_candidate_details(path)
        ranked.append((rank, path, reason))
    ranked.sort(reverse=True)

    best_rank, best_path, best_reason = ranked[0]
    if best_rank[0] <= 0:
        details = "; ".join(f"{path}: {reason}" for _rank, path, reason in ranked)
        return None, f"no candidates scored above zero ({details})"
    return best_path, f"auto-selected highest rank ({best_reason})"


def select_touch_device() -> str | None:
    selected, reason = touch_probe()
    if selected:
        print(f"[boot-selector] Touch device selected: {selected} ({reason})", flush=True)
        return selected

    print(
        (
            "[boot-selector] Warning: no suitable touch input device found; touch controls disabled. "
            f"Reason: {reason}. To force one, set TOUCH_DEVICE=/dev/input/eventX "
            "(or ROTATOR_TOUCH_DEVICE for backward compatibility)."
        ),
        flush=True,
    )
    return None


def _candidate_absinfo_paths(device: str) -> list[Path]:
    event_name = Path(device).name
    base = Path("/sys/class/input") / event_name
    candidates = [
        base / "device" / "absinfo",
        base / "device" / "device" / "absinfo",
    ]
    try:
        real = base.resolve()
        candidates.extend([real / "device" / "absinfo", real / "absinfo"])
    except Exception:
        pass

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _query_absinfo(device: str, axis: int) -> tuple[int, int] | None:
    request = eviocgabs(axis)
    payload = bytearray(INPUT_ABSINFO_STRUCT.size)
    try:
        with open(device, "rb", buffering=0) as handle:
            fcntl.ioctl(handle.fileno(), request, payload, True)
    except Exception:
        return None

    _value, minimum, maximum, _fuzz, _flat, _resolution = INPUT_ABSINFO_STRUCT.unpack(bytes(payload))
    if maximum <= minimum:
        return None
    return minimum, maximum


def detect_touch_bounds(device: str, default_width: int, default_height: int) -> tuple[int, int, int, int]:
    x_bounds = _query_absinfo(device, ABS_X) or _query_absinfo(device, ABS_MT_POSITION_X)
    y_bounds = _query_absinfo(device, ABS_Y) or _query_absinfo(device, ABS_MT_POSITION_Y)

    if x_bounds is not None and y_bounds is not None:
        x_min, x_max = x_bounds
        y_min, y_max = y_bounds
        return (x_max - x_min + 1), x_min, (y_max - y_min + 1), y_min

    x_min = 0
    y_min = 0
    x_width = default_width
    y_height = default_height

    for absinfo_path in _candidate_absinfo_paths(device):
        try:
            with open(absinfo_path, encoding="utf-8") as absinfo:
                for line in absinfo:
                    code_str, _, payload = line.partition(":")
                    if not payload:
                        continue
                    try:
                        raw_code = code_str.strip().lower()
                        code = int(raw_code, 16)
                    except ValueError:
                        try:
                            code = int(code_str.strip(), 0)
                        except ValueError:
                            continue
                    parts = payload.strip().split()
                    if len(parts) < 3:
                        continue
                    min_val = int(parts[1])
                    max_val = int(parts[2])
                    if max_val <= min_val:
                        continue
                    size = max_val - min_val + 1
                    if code in (ABS_X, ABS_MT_POSITION_X):
                        x_min = min_val
                        x_width = max(100, size)
                    elif code in (ABS_Y, ABS_MT_POSITION_Y):
                        y_min = min_val
                        y_height = max(100, size)
        except Exception:
            continue

    return x_width, x_min, y_height, y_min


def _fit_frame(frame: Image.Image, width: int, height: int) -> Image.Image:
    converted = frame.convert("RGBA")
    source_width, source_height = converted.size
    scale = min(width / source_width, height / source_height)
    scaled_width = max(1, int(source_width * scale))
    scaled_height = max(1, int(source_height * scale))
    resized = converted.resize((scaled_width, scaled_height), RESAMPLING_LANCZOS)
    canvas = Image.new("RGBA", (width, height), BACKGROUND_RGB + (255,))
    canvas.alpha_composite(resized, ((width - scaled_width) // 2, (height - scaled_height) // 2))
    return canvas.convert("RGB")


def load_selector_image(image_path: Path, width: int, height: int) -> Image.Image:
    if image_path.exists():
        with Image.open(image_path) as selector_image:
            return _fit_frame(selector_image.copy(), width, height)

    print(f"[boot-selector] Selector image not found at {image_path}; using a blank screen.", flush=True)
    return Image.new("RGB", (width, height), BACKGROUND_RGB)


def load_gif_frames(gif_path: Path, width: int, height: int, speed: float) -> list[tuple[Image.Image, float]]:
    with Image.open(gif_path) as gif:
        frames: list[tuple[Image.Image, float]] = []
        for frame in ImageSequence.Iterator(gif):
            duration_ms = max(20, int(frame.info.get("duration", DEFAULT_GIF_FRAME_MS)))
            frames.append((_fit_frame(frame.copy(), width, height), (duration_ms / 1000.0) / speed))
        return frames


def save_preview(image: Image.Image, path_like: str | None) -> None:
    if not path_like:
        return
    output_path = Path(path_like)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    print(f"Saved preview image to {output_path}", flush=True)


def playback_gif(
    framebuffer: FramebufferWriter | None,
    gif_path: Path,
    width: int,
    height: int,
    speed: float,
    output_first: str | None,
    output_last: str | None,
) -> None:
    if not gif_path.exists():
        print(f"[boot-selector] Startup GIF not found at {gif_path}; skipping animation.", flush=True)
        return

    frames = load_gif_frames(gif_path, width, height, speed)
    if not frames:
        print(f"[boot-selector] Startup GIF contains no frames: {gif_path}", flush=True)
        return

    save_preview(frames[0][0], output_first)
    save_preview(frames[-1][0], output_last)

    if framebuffer is None:
        return

    for frame, duration in frames:
        if STOP_REQUESTED:
            return
        framebuffer.write_image(frame)
        time.sleep(duration)


def _normalise_axis(raw_value: int, source_size: int, source_min: int, target_size: int) -> int:
    relative = raw_value - source_min
    if relative < 0:
        relative = 0
    elif relative >= source_size:
        relative = source_size - 1

    if source_size <= 1:
        return 0
    return int(relative * (target_size - 1) / (source_size - 1))


def _resolve_tap_mode(last_y: int, touch_height: int, touch_min_y: int, screen_height: int, invert_y: bool) -> str:
    screen_y = _normalise_axis(last_y, touch_height, touch_min_y, screen_height)
    if invert_y:
        screen_y = (screen_height - 1) - screen_y
    return "day" if screen_y < (screen_height // 2) else "night"


def wait_for_selection(
    screen_width: int,
    screen_height: int,
    touch_settle_secs: float,
    touch_debounce_secs: float,
    invert_y: bool,
) -> str | None:
    device = select_touch_device()
    if not device:
        return None

    touch_width, touch_min_x, touch_height, touch_min_y = detect_touch_bounds(device, screen_width, screen_height)
    print(
        f"[boot-selector] Waiting for touch selection on {device} (width {touch_width}, height {touch_height}); "
        f"top half selects day, bottom half selects night, invert_y={'yes' if invert_y else 'no'}.",
        flush=True,
    )

    ready_after = time.monotonic() + max(0.0, touch_settle_secs)
    last_emit = 0.0
    last_x = touch_min_x + (touch_width // 2)
    last_y = touch_min_y + (touch_height // 2)
    touch_down = False

    def commit_tap(now: float) -> str | None:
        nonlocal last_emit
        if now < ready_after or (now - last_emit) < touch_debounce_secs:
            return None
        last_emit = now
        mode = _resolve_tap_mode(last_y, touch_height, touch_min_y, screen_height, invert_y)
        print(f"[boot-selector] Selected mode: {mode} (touch_x={last_x}, touch_y={last_y})", flush=True)
        return mode

    with open(device, "rb", buffering=0) as fd:
        while not STOP_REQUESTED:
            readable, _, _ = select.select([fd], [], [], 0.2)
            if not readable:
                continue

            raw = fd.read(INPUT_EVENT_STRUCT.size)
            if len(raw) != INPUT_EVENT_STRUCT.size:
                continue

            _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)
            if ev_type == EV_ABS and ev_code in (ABS_X, ABS_MT_POSITION_X):
                last_x = ev_value
            elif ev_type == EV_ABS and ev_code in (ABS_Y, ABS_MT_POSITION_Y):
                last_y = ev_value
            elif ev_type == EV_KEY and ev_code == BTN_TOUCH:
                if ev_value == 1:
                    touch_down = True
                elif ev_value == 0 and touch_down:
                    touch_down = False
                    mode = commit_tap(time.monotonic())
                    if mode:
                        return mode
            elif ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
                if ev_value == -1 and touch_down:
                    touch_down = False
                    mode = commit_tap(time.monotonic())
                    if mode:
                        return mode
                elif ev_value >= 0:
                    touch_down = True
            elif ev_type == EV_SYN:
                continue
    return None


def run_touch_probe(width: int, height: int) -> int:
    device, reason = touch_probe()
    if not device:
        print("[boot-selector] Touch probe found no usable device.", flush=True)
        print(f"[boot-selector] Probe reason: {reason}", flush=True)
        return 1

    touch_width, touch_min_x, touch_height, touch_min_y = detect_touch_bounds(device, width, height)
    print(f"[boot-selector] Touch probe selected {device}", flush=True)
    print(f"[boot-selector] Probe reason: {reason}", flush=True)
    print(
        f"[boot-selector] Probe calibration: width={touch_width} min_x={touch_min_x} height={touch_height} min_y={touch_min_y}",
        flush=True,
    )
    return 0


def _launch_direct_mode(service_name: str) -> int:
    command = DIRECT_MODE_COMMANDS.get(service_name)
    if not command:
        print(f"[boot-selector] No direct-launch fallback is defined for {service_name}.", file=sys.stderr, flush=True)
        return 1

    print(f"[boot-selector] Falling back to direct launch for {service_name}: {command}", flush=True)
    os.execv(command[0], command)
    return 1


def launch_service(service_name: str) -> int:
    result = subprocess.run(["systemctl", "start", service_name], check=False, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[boot-selector] Started {service_name}", flush=True)
        return 0

    stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
    print(f"[boot-selector] Failed to start {service_name}: {stderr}", file=sys.stderr, flush=True)

    auth_markers = ("Authentication is required", "polkit", "Access denied", "Interactive authentication required")
    if any(marker.lower() in stderr.lower() for marker in auth_markers):
        return _launch_direct_mode(service_name)
    return result.returncode


def main() -> int:
    args = parse_args()
    validation_error = validate_args(args)
    if validation_error is not None:
        return validation_error

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    if args.probe_touch:
        return run_touch_probe(args.width, args.height)

    selector_image = load_selector_image(Path(args.selector_image), args.width, args.height)
    save_preview(selector_image, args.output_selector)

    framebuffer = None
    if not args.no_framebuffer:
        if not Path(args.fbdev).exists():
            print(f"Framebuffer {args.fbdev} not found.", file=sys.stderr)
            return 1
        framebuffer = FramebufferWriter(args.fbdev, args.width, args.height)
        framebuffer.open()

    try:
        if not args.skip_gif:
            playback_gif(framebuffer, Path(args.gif), args.width, args.height, args.gif_speed, args.output_gif_first, args.output_gif_last)
        if framebuffer is not None:
            framebuffer.write_image(selector_image)

        if args.no_framebuffer:
            print("Skipping touch loop because --no-framebuffer was set.", flush=True)
            return 0

        mode = wait_for_selection(args.width, args.height, args.touch_settle_secs, args.touch_debounce_secs, args.invert_y)
        if mode == "day":
            return launch_service(args.day_service)
        if mode == "night":
            return launch_service(args.night_service)
        return 1 if STOP_REQUESTED else 0
    finally:
        if framebuffer is not None:
            framebuffer.close()


if __name__ == "__main__":
    raise SystemExit(main())