#!/usr/bin/env python3
"""Long-running Photos slideshow app for shell child-process control."""

from __future__ import annotations

import argparse
import glob
import signal
import queue
import re
import select
import sys
import tempfile
import struct
import time
import os
import threading
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from PIL import Image

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import display as photos_display
import touch_calibration

from _config import report_validation_errors

SLEEP_SLICE_SECS = 0.25
DEFAULT_TOUCH_POLL_SECS = 0.2
DEFAULT_HOLD_TO_MENU_SECS = float(os.environ.get("PHOTOS_HOLD_TO_MENU_SECS", "1.5"))
PARENT_SHELL_MODE_REQUEST_PATH = os.environ.get("BOOT_SELECTOR_MODE_REQUEST_PATH", "").strip()
MENU_REQUEST_MODE = "menu"

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

STOP_REQUESTED = False


def request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def parse_args() -> argparse.Namespace:
    load_dotenv(photos_display.DEFAULT_ROOT / ".env")
    default_advance_secs = float(os.environ.get("PHOTOS_ADVANCE_SECS", "15"))
    parser = argparse.ArgumentParser(description="Run the Photos slideshow app until stopped by the shell.")
    parser.add_argument("--advance-secs", type=float, default=default_advance_secs, help=f"Seconds to show each slide (default: {default_advance_secs})")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logs")
    parser.add_argument("--check-config", action="store_true", help="Validate env configuration and exit")
    parser.add_argument("--self-test", action="store_true", help="Run a non-framebuffer slideshow smoke test and exit")
    parser.add_argument("--max-frames", type=int, help="Render at most this many frames before exiting")
    parser.add_argument("--no-framebuffer", action="store_true", help="Skip framebuffer writes")
    parser.add_argument("--output", help="Optional image path for the most recently rendered frame")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> int | None:
    if args.advance_secs <= 0:
        print("--advance-secs must be greater than zero.")
        return 1
    if args.max_frames is not None and args.max_frames <= 0:
        print("--max-frames must be greater than zero.")
        return 1
    return None


def build_output_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    return Path(raw_path).expanduser()


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
    has_abs_mt_x = bool(abs_mask & (1 << ABS_MT_POSITION_X))
    has_touch_abs = has_abs_x or has_abs_mt_x
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
        f"(ABS_X={'yes' if has_abs_x else 'no'}, ABS_MT_POSITION_X={'yes' if has_abs_mt_x else 'no'}); "
        f"BTN_TOUCH={'yes' if has_btn_touch else 'no'}"
    )
    return (score, int(has_touch_abs), int(has_btn_touch), -index), reason


def _resolve_forced_touch_device() -> tuple[str | None, str | None]:
    forced = os.environ.get("TOUCH_DEVICE", "").strip() or os.environ.get("PHOTOS_TOUCH_DEVICE", "").strip()
    if not forced:
        return None, None

    resolved = forced
    if forced.startswith("event") and forced[5:].isdigit():
        resolved = f"/dev/input/{forced}"

    if Path(resolved).exists():
        return resolved, f"forced by {'TOUCH_DEVICE' if os.environ.get('TOUCH_DEVICE', '').strip() else 'PHOTOS_TOUCH_DEVICE'}={forced}"
    return None, f"configured override '{forced}' was not found"


def select_touch_device() -> str | None:
    selected, reason = _resolve_forced_touch_device()
    if selected:
        print(f"[photos-slideshow.py] Touch device selected: {selected} ({reason})", flush=True)
        return selected

    candidates = sorted(glob.glob("/dev/input/event*"))
    if not candidates:
        print("[photos-slideshow.py] No /dev/input/event* devices found; touch controls disabled.", flush=True)
        return None

    ranked: list[tuple[tuple[int, int, int, int], str, str]] = []
    for path in candidates:
        rank, details = _touch_candidate_details(path)
        ranked.append((rank, path, details))
    ranked.sort(reverse=True)

    best_rank, best_path, best_reason = ranked[0]
    if best_rank[0] <= 0:
        details = "; ".join(f"{path}: {reason}" for _rank, path, reason in ranked)
        print(f"[photos-slideshow.py] No suitable touch input device found; touch controls disabled. Reason: {details}", flush=True)
        return None

    print(f"[photos-slideshow.py] Touch device selected: {best_path} ({best_reason})", flush=True)
    return best_path


def _map_touch_to_screen(raw_x: int, raw_y: int, width: int, height: int) -> tuple[int, int]:
    return touch_calibration.map_to_screen(raw_x, raw_y, width=width, height=height)


def request_parent_menu(mode_request_path: str | None = None) -> bool:
    path_text = (mode_request_path or PARENT_SHELL_MODE_REQUEST_PATH).strip()
    if not path_text:
        return False

    request_path = Path(path_text)
    request_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = request_path.with_suffix(f"{request_path.suffix}.{os.getpid()}.tmp")
    try:
        tmp_path.write_text(f"{MENU_REQUEST_MODE}\n", encoding="utf-8")
        os.replace(tmp_path, request_path)
    except OSError as exc:
        print(f"[photos-slideshow.py] Failed to request menu from shell: {exc}", file=sys.stderr, flush=True)
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        return False

    print(f"[photos-slideshow.py] Requested shell menu via {request_path}", flush=True)
    return True


def _touch_command_for_release(raw_x: int, raw_y: int, width: int, height: int, touch_started_at: float, now: float, hold_to_menu_secs: float) -> str:
    if (now - touch_started_at) >= hold_to_menu_secs:
        return MENU_REQUEST_MODE
    screen_x, _screen_y = _map_touch_to_screen(raw_x, raw_y, width, height)
    return "previous" if screen_x < (width // 2) else "next"


def touch_worker(
    event_q: "queue.Queue[str]",
    stop_evt: threading.Event,
    width: int,
    height: int,
    *,
    hold_to_menu_secs: float = DEFAULT_HOLD_TO_MENU_SECS,
    poll_timeout_secs: float = DEFAULT_TOUCH_POLL_SECS,
) -> None:
    device = select_touch_device()
    if not device:
        return

    touch_down = False
    touch_started_at = 0.0
    saw_explicit_touch_state = False
    pending_abs_sample = False
    last_x = width // 2
    last_y = height // 2
    last_synthetic_sample_at = 0.0
    synthetic_touch_timeout_secs = max(0.35, poll_timeout_secs * 2)

    try:
        with open(device, "rb", buffering=0) as fd:
            while not stop_evt.is_set():
                readable, _, _ = select.select([fd], [], [], poll_timeout_secs)
                now = time.monotonic()
                if not readable:
                    if touch_down and not saw_explicit_touch_state and last_synthetic_sample_at and (now - last_synthetic_sample_at) >= synthetic_touch_timeout_secs:
                        event_q.put(_touch_command_for_release(last_x, last_y, width, height, touch_started_at, now, hold_to_menu_secs))
                        touch_down = False
                    continue

                raw = fd.read(INPUT_EVENT_STRUCT.size)
                if len(raw) != INPUT_EVENT_STRUCT.size:
                    continue

                _sec, _usec, ev_type, ev_code, ev_value = INPUT_EVENT_STRUCT.unpack(raw)

                if ev_type == EV_ABS and ev_code in (ABS_X, ABS_MT_POSITION_X):
                    last_x = ev_value
                    pending_abs_sample = True
                elif ev_type == EV_ABS and ev_code in (ABS_Y, ABS_MT_POSITION_Y):
                    last_y = ev_value
                    pending_abs_sample = True
                elif ev_type == EV_KEY and ev_code == BTN_TOUCH:
                    saw_explicit_touch_state = True
                    if ev_value == 1:
                        touch_down = True
                        touch_started_at = now
                    elif ev_value == 0 and touch_down:
                        touch_down = False
                        event_q.put(_touch_command_for_release(last_x, last_y, width, height, touch_started_at, now, hold_to_menu_secs))
                elif ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
                    saw_explicit_touch_state = True
                    if ev_value >= 0:
                        touch_down = True
                        touch_started_at = now
                    elif ev_value == -1 and touch_down:
                        touch_down = False
                        event_q.put(_touch_command_for_release(last_x, last_y, width, height, touch_started_at, now, hold_to_menu_secs))
                elif ev_type == EV_SYN and pending_abs_sample and not saw_explicit_touch_state:
                    pending_abs_sample = False
                    if not touch_down:
                        touch_down = True
                        touch_started_at = now
                    last_synthetic_sample_at = now
                elif ev_type == EV_SYN:
                    continue
    except Exception as exc:
        print(f"[photos-slideshow.py] Touch worker stopped ({device}): {exc}", flush=True)


def _advance_history(current_image: Path, history: list[Path]) -> None:
    history.append(current_image)


def _rewind_history(current_image: Path, history: list[Path]) -> Path:
    if history:
        return history.pop()
    return current_image


def present_frame(
    frame: Image.Image,
    config: photos_display.Config,
    log: photos_display.Log,
    *,
    no_framebuffer: bool,
    output_path: Path | None,
) -> None:
    if output_path is not None:
        photos_display.save_frame(frame, output_path)
        log.info(f"Saved slideshow frame: {output_path}")
    if no_framebuffer:
        return

    used_fallback = photos_display.write_framebuffer_with_fallback(frame, config, log)
    if used_fallback:
        log.info(f"Rendered fallback slideshow frame to {config.fb_device}")
    else:
        log.info(f"Rendered slideshow frame to {config.fb_device}")


def run_slideshow(
    config: photos_display.Config,
    log: photos_display.Log,
    *,
    advance_secs: float,
    no_framebuffer: bool = False,
    output_path: Path | None = None,
    max_frames: int | None = None,
    stop_requested: Callable[[], bool] | None = None,
    touch_event_q: "queue.Queue[str]" | None = None,
    request_menu_fn: Callable[[str | None], bool] = request_parent_menu,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    should_stop = stop_requested or (lambda: STOP_REQUESTED)
    frames_rendered = 0
    history: list[Path] = []
    current_image = photos_display.select_source_image(config, log)
    touch_events: "queue.Queue[str]" = touch_event_q or queue.Queue()
    touch_stop_evt = threading.Event()
    touch_thread: threading.Thread | None = None

    if not no_framebuffer and touch_event_q is None:
        touch_thread = threading.Thread(
            target=touch_worker,
            args=(touch_events, touch_stop_evt, config.width, config.height),
            daemon=True,
        )
        touch_thread.start()

    try:
        while not should_stop():
            try:
                frame = photos_display.render_frame_with_fallback(current_image, config, log)
                present_frame(
                    frame,
                    config,
                    log,
                    no_framebuffer=no_framebuffer,
                    output_path=output_path,
                )
            except RuntimeError as exc:
                print(str(exc))
                return 1

            frames_rendered += 1
            if max_frames is not None and frames_rendered >= max_frames:
                return 0

            deadline = time.monotonic() + advance_secs
            while not should_stop():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _advance_history(current_image, history)
                    current_image = photos_display.select_source_image(config, log)
                    break

                wait_secs = min(SLEEP_SLICE_SECS, remaining)
                try:
                    touch_command = touch_events.get(timeout=wait_secs)
                except queue.Empty:
                    sleep_fn(0.0)
                    continue

                if touch_command == MENU_REQUEST_MODE:
                    if request_menu_fn(PARENT_SHELL_MODE_REQUEST_PATH or None):
                        return 0
                    continue
                if touch_command == "previous":
                    current_image = _rewind_history(current_image, history)
                    break
                if touch_command == "next":
                    _advance_history(current_image, history)
                    current_image = photos_display.select_source_image(config, log)
                    break
    finally:
        touch_stop_evt.set()
        if touch_thread is not None:
            touch_thread.join(timeout=1.0)

    log.info("Stop requested; exiting slideshow.")
    return 0


def run_self_test(log: photos_display.Log) -> int:
    with tempfile.TemporaryDirectory(prefix="photos-slideshow-") as temp_dir:
        temp_root = Path(temp_dir)
        output_path = temp_root / "self-test.png"
        local_dir = temp_root / "local"
        local_dir.mkdir(parents=True, exist_ok=True)
        sample_path = local_dir / "sample.png"
        Image.new("RGB", (640, 480), color=(12, 34, 56)).save(sample_path)

        config = photos_display.Config(
            local_photos_dir=local_dir,
            album_id="",
            drive_folder_id="",
            drive_sync_state_path=temp_root / "drive-sync-state.json",
            client_secrets_path=temp_root / "client_secret.json",
            client_id="",
            client_secret="",
            token_path=temp_root / "token_photos.json",
            fb_device="/dev/null",
            width=320,
            height=240,
            cache_dir=temp_root / "cache",
            fallback_image=MODULE_DIR / "photos-fallback.png",
            logo_path=MODULE_DIR / ".no-logo",
            oauth_port=8080,
            oauth_open_browser=False,
        )

        rc = run_slideshow(
            config,
            log,
            advance_secs=0.01,
            no_framebuffer=True,
            output_path=output_path,
            max_frames=2,
            stop_requested=lambda: False,
        )
        if rc != 0 or not output_path.exists():
            print("Photos slideshow self-test failed.")
            return 1

        print(f"[photos-slideshow.py] Self-test passed: {output_path}")
    return 0


def main() -> int:
    args = parse_args()
    invalid = validate_args(args)
    if invalid is not None:
        return invalid

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    log = photos_display.Log(debug=args.debug)

    if args.self_test:
        return run_self_test(log)

    load_dotenv(photos_display.DEFAULT_ROOT / ".env")
    config, errors = photos_display.validate_config()
    if errors:
        report_validation_errors("photos-slideshow.py", errors)
        return 1
    assert config is not None

    if args.check_config:
        print("[photos-slideshow.py] Configuration check passed.")
        return 0

    return run_slideshow(
        config,
        log,
        advance_secs=args.advance_secs,
        no_framebuffer=args.no_framebuffer,
        output_path=build_output_path(args.output),
        max_frames=args.max_frames,
    )


if __name__ == "__main__":
    raise SystemExit(main())
