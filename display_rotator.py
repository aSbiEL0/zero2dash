#!/usr/bin/env python3
"""Rotate multiple framebuffer dashboard scripts during day mode.

Features:
- Timed page rotation across standalone scripts
- Touch controls:
  - tap left side  -> previous page
  - tap right side -> next page
  - double tap     -> screen off/on
"""

from __future__ import annotations

import fcntl
import glob
import os
import queue
import select
import signal
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path


DEFAULT_PAGES_DIR = "scripts"
DEFAULT_PAGE_GLOB = "*.py"
DEFAULT_EXCLUDE_PATTERNS = ["pihole-display-dark*.py"]
DEFAULT_ROTATE_SECS = 30
SHUTDOWN_WAIT_SECS = 5
DEFAULT_FBDEV = "/dev/fb1"
DEFAULT_WIDTH = 320
DOUBLE_TAP_WINDOW_SECS = 0.35

# linux/input-event-codes.h
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03
ABS_X = 0x00
ABS_MT_POSITION_X = 0x35
BTN_TOUCH = 0x14A
INPUT_EVENT_STRUCT = struct.Struct("llHHI")

# linux/fb.h
FBIOBLANK = 0x4611
FB_BLANK_UNBLANK = 0
FB_BLANK_POWERDOWN = 4


class ScreenPower:
    def __init__(self, fbdev: str) -> None:
        self.fbdev = fbdev
        self.screen_on = True

    def toggle(self) -> None:
        target = FB_BLANK_POWERDOWN if self.screen_on else FB_BLANK_UNBLANK
        try:
            with open(self.fbdev, "rb", buffering=0) as fb:
                fcntl.ioctl(fb.fileno(), FBIOBLANK, target)
            self.screen_on = not self.screen_on
            print(f"[rotator] Screen {'ON' if self.screen_on else 'OFF'}", flush=True)
        except Exception as exc:
            print(f"[rotator] Screen toggle failed on {self.fbdev}: {exc}", flush=True)


def parse_exclude_patterns() -> list[str]:
    raw = os.environ.get("ROTATOR_EXCLUDE_PATTERNS", "").strip()
    if raw:
        return [entry.strip() for entry in raw.split(",") if entry.strip()]
    return DEFAULT_EXCLUDE_PATTERNS.copy()


def discover_pages(base_dir: Path) -> list[str]:
    page_dir_raw = os.environ.get("ROTATOR_PAGES_DIR", DEFAULT_PAGES_DIR).strip() or DEFAULT_PAGES_DIR
    page_glob = os.environ.get("ROTATOR_PAGE_GLOB", DEFAULT_PAGE_GLOB).strip() or DEFAULT_PAGE_GLOB
    excludes = parse_exclude_patterns()

    page_dir = Path(page_dir_raw)
    if not page_dir.is_absolute():
        page_dir = base_dir / page_dir

    if not page_dir.exists():
        print(f"[rotator] Page directory does not exist: {page_dir}", flush=True)
        return []

    discovered: list[str] = []
    for path in sorted(page_dir.glob(page_glob)):
        if not path.is_file():
            continue
        if any(path.match(pattern) or path.name == pattern for pattern in excludes):
            continue
        discovered.append(str(path.relative_to(base_dir)))

    return discovered


def parse_pages(base_dir: Path) -> list[str]:
    # Backward-compatible manual override; otherwise scan a directory.
    raw = os.environ.get("ROTATOR_PAGES", "").strip()
    if raw:
        return [entry.strip() for entry in raw.split(",") if entry.strip()]
    return discover_pages(base_dir)


def parse_rotate_secs() -> int:
    raw = os.environ.get("ROTATOR_SECS", str(DEFAULT_ROTATE_SECS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_ROTATE_SECS
    return max(5, value)


def parse_width() -> int:
    raw = os.environ.get("ROTATOR_TOUCH_WIDTH", str(DEFAULT_WIDTH)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_WIDTH
    return max(100, value)


def detect_touch_width(device: str, default_width: int) -> int:
    absinfo_path = Path("/sys/class/input") / Path(device).name / "device" / "absinfo"
    try:
        with open(absinfo_path) as absinfo:
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
                if code not in (ABS_X, ABS_MT_POSITION_X):
                    continue

                parts = payload.strip().split()
                if len(parts) < 3:
                    continue
                try:
                    min_val = int(parts[1])
                    max_val = int(parts[2])
                except ValueError:
                    continue

                if max_val > min_val:
                    width = max_val - min_val + 1
                    return max(default_width, width)
    except Exception as exc:
        print(f"[rotator] Touch width detection failed ({device}): {exc}", flush=True)
    return default_width


def resolve_script(path_like: str, base_dir: Path) -> str | None:
    path = Path(path_like)
    candidates = [path] if path.is_absolute() else [base_dir / path, base_dir / "scripts" / path]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    checked = ", ".join(str(candidate) for candidate in candidates)
    print(f"[rotator] Skipping missing page '{path_like}' (checked: {checked})", flush=True)
    return None


def stop_child(child: subprocess.Popen[bytes] | None) -> None:
    if child is None or child.poll() is not None:
        return

    child.terminate()
    try:
        child.wait(timeout=SHUTDOWN_WAIT_SECS)
        return
    except subprocess.TimeoutExpired:
        pass

    child.kill()
    child.wait(timeout=SHUTDOWN_WAIT_SECS)


def launch_page(script_path: str) -> subprocess.Popen[bytes]:
    print(f"[rotator] Launching {script_path}", flush=True)
    return subprocess.Popen([sys.executable, "-u", script_path])


def select_touch_device() -> str | None:
    forced = os.environ.get("ROTATOR_TOUCH_DEVICE", "").strip()
    if forced:
        return forced if Path(forced).exists() else None
    candidates = sorted(glob.glob("/dev/input/event*"))
    return candidates[0] if candidates else None


def touch_worker(cmd_q: "queue.Queue[str]", stop_evt: threading.Event, touch_width: int) -> None:
    device = select_touch_device()
    if not device:
        print("[rotator] No touch device found; touch controls disabled.", flush=True)
        return

    device_touch_width = detect_touch_width(device, touch_width)
    print(f"[rotator] Touch controls listening on {device} (width {device_touch_width})", flush=True)

    last_x = device_touch_width // 2
    touch_down = False
    last_tap_ts = 0.0

    try:
        with open(device, "rb", buffering=0) as fd:
            while not stop_evt.is_set():
                readable, _, _ = select.select([fd], [], [], 0.2)
                if not readable:
                    continue

                raw = fd.read(INPUT_EVENT_STRUCT.size)
                if len(raw) != INPUT_EVENT_STRUCT.size:
                    continue

                _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)

                if ev_type == EV_ABS and ev_code in (ABS_X, ABS_MT_POSITION_X):
                    last_x = ev_value
                elif ev_type == EV_KEY and ev_code == BTN_TOUCH:
                    if ev_value == 1:
                        touch_down = True
                    elif ev_value == 0 and touch_down:
                        touch_down = False
                        now = time.monotonic()
                        if now - last_tap_ts <= DOUBLE_TAP_WINDOW_SECS:
                            cmd_q.put("TOGGLE_SCREEN")
                            last_tap_ts = 0.0
                        else:
                            cmd_q.put("PREV" if last_x < (device_touch_width // 2) else "NEXT")
                            last_tap_ts = now
                elif ev_type == EV_SYN:
                    continue
    except Exception as exc:
        print(f"[rotator] Touch worker stopped ({device}): {exc}", flush=True)


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    rotate_secs = parse_rotate_secs()
    touch_width = parse_width()
    fbdev = os.environ.get("ROTATOR_FBDEV", DEFAULT_FBDEV)

    pages = [
        resolved
        for resolved in (resolve_script(item, base_dir) for item in parse_pages(base_dir))
        if resolved is not None
    ]

    if len(pages) == 1:
        print(
            "[rotator] Only one valid page configured; rotation and swipe navigation will reload that same script.",
            flush=True,
        )

    if not pages:
        print("[rotator] No valid pages found; exiting.", file=sys.stderr, flush=True)
        return 1

    active_child: subprocess.Popen[bytes] | None = None
    stop_requested = False
    cmd_q: queue.Queue[str] = queue.Queue()
    stop_evt = threading.Event()
    screen = ScreenPower(fbdev)

    worker = threading.Thread(target=touch_worker, args=(cmd_q, stop_evt, touch_width), daemon=True)
    worker.start()

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        print(f"[rotator] Received signal {signum}; stopping.", flush=True)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    index = 0
    while not stop_requested:
        script = pages[index]
        active_child = launch_page(script)

        rotate_due = time.monotonic() + rotate_secs
        next_index = (index + 1) % len(pages)

        while not stop_requested:
            if active_child.poll() is not None:
                print(
                    f"[rotator] Page exited early with code {active_child.returncode}: {script}",
                    flush=True,
                )
                break

            if time.monotonic() >= rotate_due:
                break

            try:
                command = cmd_q.get(timeout=0.2)
            except queue.Empty:
                continue

            if command == "TOGGLE_SCREEN":
                screen.toggle()
            elif command == "NEXT":
                next_index = (index + 1) % len(pages)
                break
            elif command == "PREV":
                next_index = (index - 1) % len(pages)
                break

        stop_child(active_child)
        active_child = None
        index = next_index

    stop_evt.set()
    stop_child(active_child)
    print("[rotator] Exit complete.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
