"""Touch input helpers for the dashboard rotator."""

from __future__ import annotations

import glob
import os
import queue
import re
import select
import struct
import threading
import time
from pathlib import Path

import touch_calibration

DOUBLE_TAP_WINDOW_SECS = 0.25
HOLD_TO_SELECTOR_SECS = float(os.environ.get("ROTATOR_HOLD_TO_SELECTOR_SECS", "3.0"))

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


def detect_touch_width(device: str, default_width: int) -> tuple[int, int]:
    for absinfo_path in _candidate_absinfo_paths(device):
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
                        return max(100, width), min_val
        except Exception:
            continue

    print(f"[rotator] Touch width detection failed ({device}); using width {default_width}", flush=True)
    return default_width, 0


def _candidate_absinfo_paths(device: str) -> list[Path]:
    event_name = Path(device).name
    base = Path("/sys/class/input") / event_name
    candidates = [
        base / "device" / "absinfo",
        base / "device" / "device" / "absinfo",
    ]
    try:
        real = base.resolve()
        candidates.extend([
            real / "device" / "absinfo",
            real / "absinfo",
        ])
    except Exception:
        pass

    uniq: list[Path] = []
    seen: set[Path] = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


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
    forced = os.environ.get("TOUCH_DEVICE", "").strip() or os.environ.get("ROTATOR_TOUCH_DEVICE", "").strip()
    if not forced:
        return None, None

    resolved = forced
    if forced.startswith("event") and forced[5:].isdigit():
        resolved = f"/dev/input/{forced}"

    if Path(resolved).exists():
        return resolved, f"forced by {'TOUCH_DEVICE' if os.environ.get('TOUCH_DEVICE', '').strip() else 'ROTATOR_TOUCH_DEVICE'}={forced}"
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
        print(f"[rotator] Touch device selected: {selected} ({reason})", flush=True)
        return selected

    print(
        (
            "[rotator] Warning: no suitable touch input device found; touch controls disabled. "
            f"Reason: {reason}. To force one, set TOUCH_DEVICE=/dev/input/eventX "
            "(or ROTATOR_TOUCH_DEVICE for backward compatibility)."
        ),
        flush=True,
    )
    return None


def touch_worker(cmd_q: "queue.Queue[str]", stop_evt: threading.Event, touch_width: int, tap_debounce_secs: float) -> None:
    device = select_touch_device()
    if not device:
        print("[rotator] No touch device found; touch controls disabled.", flush=True)
        return

    use_calibration = touch_calibration.applies_to(device)
    if use_calibration:
        device_touch_width = touch_width
        device_touch_min = 0
        print(f"[rotator] Touch controls listening on {device} (shared calibration)", flush=True)
    else:
        device_touch_width, device_touch_min = detect_touch_width(device, touch_width)
        print(f"[rotator] Touch controls listening on {device} (width {device_touch_width})", flush=True)

    last_x = device_touch_min + (device_touch_width // 2)
    last_y = 0
    touch_down = False
    touch_started_at = 0.0
    last_tap_ts = None
    last_emit = 0.0
    saw_explicit_touch_state = False
    pending_abs_sample = False
    last_synthetic_sample_at = 0.0
    synthetic_touch_timeout_secs = 0.35

    def emit_tap(raw_x: int, raw_y: int, now: float) -> None:
        nonlocal last_tap_ts, last_emit
        if (now - touch_started_at) >= HOLD_TO_SELECTOR_SECS:
            cmd_q.put("MAIN_MENU")
            last_tap_ts = None
            last_emit = now
            return

        if use_calibration:
            relative_x, _screen_y = touch_calibration.map_to_screen(raw_x, raw_y, width=touch_width, height=1)
        else:
            relative_x = raw_x - device_touch_min
            if relative_x < 0:
                relative_x = 0
            elif relative_x >= device_touch_width:
                relative_x = device_touch_width - 1

        if last_tap_ts is not None and (now - last_tap_ts) <= DOUBLE_TAP_WINDOW_SECS:
            if (now - last_emit) >= tap_debounce_secs:
                cmd_q.put("TOGGLE_SCREEN")
                last_emit = now
            last_tap_ts = None
            return

        if (now - last_emit) >= tap_debounce_secs:
            cmd_q.put("PREV" if relative_x < (touch_width // 2) else "NEXT")
            last_emit = now
        last_tap_ts = now

    try:
        with open(device, "rb", buffering=0) as fd:
            while not stop_evt.is_set():
                readable, _, _ = select.select([fd], [], [], 0.2)
                if not readable:
                    now = time.monotonic()
                    if touch_down and not saw_explicit_touch_state and last_synthetic_sample_at:
                        if (now - touch_started_at) >= HOLD_TO_SELECTOR_SECS and (now - last_synthetic_sample_at) < synthetic_touch_timeout_secs:
                            touch_down = False
                            emit_tap(last_x, last_y, now)
                        elif (now - last_synthetic_sample_at) >= synthetic_touch_timeout_secs:
                            touch_down = False
                            emit_tap(last_x, last_y, now)
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
                        touch_started_at = time.monotonic()
                    elif ev_value == 0 and touch_down:
                        touch_down = False
                        emit_tap(last_x, last_y, time.monotonic())
                elif ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
                    saw_explicit_touch_state = True
                    if ev_value == -1 and touch_down:
                        touch_down = False
                        emit_tap(last_x, last_y, time.monotonic())
                    elif ev_value >= 0:
                        touch_down = True
                        touch_started_at = time.monotonic()
                elif ev_type == EV_SYN and pending_abs_sample and not saw_explicit_touch_state:
                    pending_abs_sample = False
                    now = time.monotonic()
                    if not touch_down:
                        touch_down = True
                        touch_started_at = now
                    last_synthetic_sample_at = now
                elif ev_type == EV_SYN:
                    continue
    except Exception as exc:
        print(f"[rotator] Touch worker stopped ({device}): {exc}", flush=True)


def run_touch_probe(default_width: int) -> int:
    device, reason = touch_probe()
    if device:
        width, min_x = detect_touch_width(device, default_width)
        print(f"[rotator] Touch probe selected {device}", flush=True)
        print(f"[rotator] Probe reason: {reason}", flush=True)
        print(f"[rotator] Probe width calibration: width={width} min_x={min_x}", flush=True)
        return 0

    print("[rotator] Touch probe found no usable device.", flush=True)
    print(f"[rotator] Probe reason: {reason}", flush=True)
    print(
        "[rotator] Hint: export TOUCH_DEVICE=/dev/input/eventX to force the touchscreen device.",
        flush=True,
    )
    return 1
