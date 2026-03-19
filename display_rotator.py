#!/usr/bin/env python3
"""Rotate multiple framebuffer dashboard scripts during day mode.

Features:
- Timed page rotation across standalone scripts
- Touch controls:
  - tap left side  -> previous page
  - tap right side -> next page
  - double tap     -> screen off/on
  - hold 3 seconds -> main menu
"""

from __future__ import annotations

import argparse
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from rotator.power import ScreenPower
from rotator.touch import run_touch_probe, touch_worker
from rotator.backoff import calculate_backoff_secs, format_failure_reason
from rotator.config import (
    parse_backoff_max_secs,
    parse_quarantine_cycles,
    parse_quarantine_failure_threshold,
    parse_rotate_secs,
    parse_tap_debounce,
    parse_width,
)
from rotator import discovery as rotator_discovery


SHUTDOWN_WAIT_SECS = 5
DEFAULT_FBDEV = "/dev/fb1"
BASE_DIR = Path(__file__).resolve().parent
BOOT_SELECTOR_SCRIPT = BASE_DIR / "boot" / "boot_selector.py"
BOOT_SELECTOR_SERVICE = os.environ.get("ROTATOR_BOOT_SELECTOR_SERVICE", "boot-selector.service").strip() or "boot-selector.service"



def _resolve_path(raw_path: str, *, base_dir: Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    return path


def parse_pages(base_dir: Path, list_pages: bool = False) -> list[str]:
    # Backward-compatible manual override; otherwise scan a directory.
    raw = os.environ.get("ROTATOR_PAGES", "").strip()
    if raw:
        return [entry.strip() for entry in raw.split(",") if entry.strip()]
    return discover_pages(base_dir, list_pages=list_pages, resolve_path=lambda raw_path, root: _resolve_path(raw_path, base_dir=root))


def resolve_page_specs(page_entries: list[str], base_dir: Path, default_dwell_secs: int) -> list[tuple[str, int]]:
    return rotator_discovery.resolve_page_specs(
        page_entries,
        base_dir,
        default_dwell_secs,
        resolve_script=resolve_script,
        resolve_path=lambda raw_path, root: _resolve_path(raw_path, base_dir=root),
    )


def discover_pages(base_dir: Path, list_pages: bool = False) -> list[str]:
    return rotator_discovery.discover_pages(
        base_dir,
        list_pages=list_pages,
        resolve_path=lambda raw_path, root: _resolve_path(raw_path, base_dir=root),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rotate dashboard page scripts on the framebuffer display.")
    parser.add_argument(
        "--list-pages",
        action="store_true",
        help="Print discovered scripts and why each one is included/excluded, then exit.",
    )
    parser.add_argument(
        "--probe-touch",
        action="store_true",
        help="Probe touch input selection and print the chosen device/reason, then exit.",
    )
    return parser.parse_args(argv)


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


def activate_boot_selector() -> int:
    running_under_systemd = bool(os.environ.get("INVOCATION_ID", "").strip())
    if running_under_systemd:
        result = subprocess.run(["systemctl", "start", BOOT_SELECTOR_SERVICE], check=False, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[rotator] Long press detected; started {BOOT_SELECTOR_SERVICE}.", flush=True)
            return 0

        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        print(f"[rotator] Failed to start {BOOT_SELECTOR_SERVICE}: {stderr}", file=sys.stderr, flush=True)
        return result.returncode

    if not BOOT_SELECTOR_SCRIPT.exists():
        print(f"[rotator] Boot selector script not found: {BOOT_SELECTOR_SCRIPT}", file=sys.stderr, flush=True)
        return 1

    manual_env = os.environ.copy()
    manual_env.pop("INVOCATION_ID", None)
    subprocess.Popen(
        [sys.executable, "-u", str(BOOT_SELECTOR_SCRIPT)],
        cwd=str(BASE_DIR),
        env=manual_env,
        start_new_session=True,
    )
    print(f"[rotator] Long press detected; launched {BOOT_SELECTOR_SCRIPT} manually.", flush=True)
    return 0


def main() -> int:
    args = parse_args(sys.argv[1:])
    base_dir = Path(__file__).resolve().parent
    rotate_secs = parse_rotate_secs()
    touch_width = parse_width()
    tap_debounce_secs = parse_tap_debounce()
    quarantine_failure_threshold = parse_quarantine_failure_threshold()
    quarantine_cycles = parse_quarantine_cycles()
    backoff_cap_secs = parse_backoff_max_secs()
    fbdev = os.environ.get("ROTATOR_FBDEV", DEFAULT_FBDEV)

    if args.probe_touch:
        return run_touch_probe(touch_width)

    page_specs = resolve_page_specs(parse_pages(base_dir, list_pages=args.list_pages), base_dir, rotate_secs)
    pages = [script for script, _dwell_secs in page_specs]
    page_dwell_secs = {script: dwell_secs for script, dwell_secs in page_specs}

    if args.list_pages:
        return 0 if pages else 1

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

    worker = threading.Thread(target=touch_worker, args=(cmd_q, stop_evt, touch_width, tap_debounce_secs), daemon=True)
    worker.start()

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        print(f"[rotator] Received signal {signum}; stopping.", flush=True)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    page_state = {
        script: {
            "consecutive_failures": 0,
            "last_failure_ts": 0.0,
            "retry_after": 0.0,
            "quarantine_cycles_remaining": 0,
        }
        for script in pages
    }

    index = 0
    while not stop_requested:
        script = pages[index]
        state = page_state[script]
        if state["quarantine_cycles_remaining"] > 0:
            state["quarantine_cycles_remaining"] -= 1
            print(
                (
                    f"[rotator] Quarantine skip: {script} "
                    f"(remaining cycles: {state['quarantine_cycles_remaining']})"
                ),
                flush=True,
            )
            index = (index + 1) % len(pages)
            continue

        now = time.monotonic()
        if state["retry_after"] > now:
            retry_in = max(1, int(state["retry_after"] - now))
            print(f"[rotator] Backoff skip: {script} (retry in {retry_in}s)", flush=True)
            index = (index + 1) % len(pages)
            continue

        active_child = launch_page(script)

        rotate_due = time.monotonic() + page_dwell_secs.get(script, rotate_secs)
        next_index = (index + 1) % len(pages)
        early_exit = False
        completed_full_duration = False
        last_returncode: int | None = None

        while not stop_requested:
            if active_child.poll() is not None:
                early_exit = True
                last_returncode = active_child.returncode
                print(
                    f"[rotator] Page exited early with code {last_returncode}: {script}",
                    flush=True,
                )
                active_child = None
                # Keep static pages visible for ROTATOR_SECS even if script exits immediately.
                while not stop_requested and time.monotonic() < rotate_due:
                    try:
                        command = cmd_q.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    if command == "TOGGLE_SCREEN":
                        screen.toggle()
                    elif command == "MAIN_MENU":
                        stop_requested = True
                        rotate_due = 0
                        break
                    elif command == "NEXT":
                        next_index = (index + 1) % len(pages)
                        rotate_due = 0
                        break
                    elif command == "PREV":
                        next_index = (index - 1) % len(pages)
                        rotate_due = 0
                        break
                break

            if time.monotonic() >= rotate_due:
                completed_full_duration = True
                break

            try:
                command = cmd_q.get(timeout=0.2)
            except queue.Empty:
                continue

            if command == "TOGGLE_SCREEN":
                screen.toggle()
            elif command == "MAIN_MENU":
                stop_requested = True
                break
            elif command == "NEXT":
                next_index = (index + 1) % len(pages)
                break
            elif command == "PREV":
                next_index = (index - 1) % len(pages)
                break

        stop_child(active_child)
        active_child = None

        if stop_requested:
            launch_status = activate_boot_selector()
            if launch_status != 0:
                return launch_status
            break

        if early_exit and (last_returncode is None or last_returncode != 0):
            state["consecutive_failures"] += 1
            state["last_failure_ts"] = time.time()
            backoff_secs = calculate_backoff_secs(state["consecutive_failures"], backoff_cap_secs)
            state["retry_after"] = time.monotonic() + backoff_secs
            reason = format_failure_reason(last_returncode)
            retry_wall_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + backoff_secs))
            print(
                (
                    f"[rotator] Failure recorded for {script}: {reason}; "
                    f"consecutive_failures={state['consecutive_failures']} "
                    f"next_retry={retry_wall_time}"
                ),
                flush=True,
            )

            if state["consecutive_failures"] >= quarantine_failure_threshold:
                state["quarantine_cycles_remaining"] = quarantine_cycles
                print(
                    (
                        f"[rotator] Quarantining {script} for {quarantine_cycles} cycles "
                        f"after {state['consecutive_failures']} consecutive failures."
                    ),
                    flush=True,
                )
        elif completed_full_duration or (early_exit and last_returncode == 0):
            if early_exit and last_returncode == 0:
                print(f"[rotator] Clean one-shot page completed: {script}", flush=True)
            if state["consecutive_failures"] > 0 or state["quarantine_cycles_remaining"] > 0:
                print(f"[rotator] Resetting failure counters after successful run: {script}", flush=True)
            state["consecutive_failures"] = 0
            state["last_failure_ts"] = 0.0
            state["retry_after"] = 0.0
            state["quarantine_cycles_remaining"] = 0

        index = next_index

    stop_evt.set()
    stop_child(active_child)
    print("[rotator] Exit complete.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



