#!/usr/bin/env python3
"""Long-running Photos slideshow app for shell child-process control."""

from __future__ import annotations

import argparse
import signal
import sys
import tempfile
import time
import os
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

from _config import report_validation_errors

SLEEP_SLICE_SECS = 0.25

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
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    should_stop = stop_requested or (lambda: STOP_REQUESTED)
    frames_rendered = 0

    while not should_stop():
        source_image = photos_display.select_source_image(config, log)
        try:
            frame = photos_display.render_frame_with_fallback(source_image, config, log)
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
                break
            sleep_fn(min(SLEEP_SLICE_SECS, remaining))

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
