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
import json
import os
import argparse
import re
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
DEFAULT_EXCLUDE_PATTERNS = [
    "piholestats_v1.2.py",
    "calendash-api.py",
    "_config.py",
    "drive-sync.py",
    "photo-resize.py",
]
DEFAULT_INCLUDE_PATTERNS: list[str] = []
DEFAULT_ROTATE_SECS = 30
SHUTDOWN_WAIT_SECS = 5
DEFAULT_FBDEV = "/dev/fb1"
DEFAULT_WIDTH = 320
DOUBLE_TAP_WINDOW_SECS = 0.35
TAP_DEBOUNCE_SECS = 0.20
DEFAULT_FB_BLANK_FAILURE_THRESHOLD = 3
DEFAULT_POWER_SUMMARY_INTERVAL_SECS = 300
DEFAULT_BACKOFF_STEPS = (10, 30, 60)
DEFAULT_BACKOFF_MAX_SECS = 300
DEFAULT_QUARANTINE_FAILURE_THRESHOLD = 3
DEFAULT_QUARANTINE_CYCLES = 3

DISCOVERY_CONFIG_DOCS = [
    {
        "env": "ROTATOR_PAGES_DIR",
        "default": DEFAULT_PAGES_DIR,
        "description": "Directory to scan for page scripts.",
    },
    {
        "env": "ROTATOR_PAGE_GLOB",
        "default": DEFAULT_PAGE_GLOB,
        "description": "Comma-separated glob(s) used to discover page scripts.",
    },
    {
        "env": "ROTATOR_INCLUDE_PATTERNS",
        "default": "",
        "description": "Optional comma-separated exact filename/path or glob patterns to force-include.",
    },
    {
        "env": "ROTATOR_EXCLUDE_PATTERNS",
        "default": ",".join(DEFAULT_EXCLUDE_PATTERNS),
        "description": "Comma-separated exact filename/path or glob patterns to exclude.",
    },
]

# linux/input-event-codes.h
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03
ABS_X = 0x00
ABS_MT_POSITION_X = 0x35
ABS_MT_TRACKING_ID = 0x39
BTN_TOUCH = 0x14A
INPUT_EVENT_STRUCT = struct.Struct("llHHI")

# linux/fb.h
FBIOBLANK = 0x4611
FB_BLANK_UNBLANK = 0
FB_BLANK_POWERDOWN = 4


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value.strip())
    except (AttributeError, ValueError):
        return default


def _read_int_file(path: Path, default: int) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return default


def _read_virtual_size(path: Path) -> tuple[int, int] | None:
    try:
        width_raw, height_raw = path.read_text(encoding="utf-8").strip().split(",", 1)
        width = int(width_raw)
        height = int(height_raw)
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


class ScreenPower:
    def __init__(self, fbdev: str) -> None:
        self.fbdev = fbdev
        self.screen_on = True
        self._fb_blank_supported = True
        self._fb_blank_failure_threshold = max(
            1,
            _safe_int(os.environ.get("ROTATOR_FB_BLANK_FAILURE_THRESHOLD", str(DEFAULT_FB_BLANK_FAILURE_THRESHOLD)), DEFAULT_FB_BLANK_FAILURE_THRESHOLD),
        )
        self._power_summary_interval_secs = max(
            30,
            _safe_int(os.environ.get("ROTATOR_POWER_SUMMARY_INTERVAL_SECS", str(DEFAULT_POWER_SUMMARY_INTERVAL_SECS)), DEFAULT_POWER_SUMMARY_INTERVAL_SECS),
        )
        self._status_file = os.environ.get("ROTATOR_STATUS_FILE", "").strip()
        self._fb_blank_consecutive_failures = 0
        self._fb_blank_failures_total = 0
        self._fb_blank_success_total = 0
        self._fb_blank_disable_reason = ""
        self._black_fill_success_total = 0
        self._black_fill_failures_total = 0
        self._last_toggle_method = "startup"
        self._last_toggle_success = True
        self._last_toggle_error = ""
        self._last_summary_ts = 0.0

        print(
            (
                "[rotator] Warning: FBIOBLANK failures are tracked. "
                f"After {self._fb_blank_failure_threshold} consecutive failures on {self.fbdev}, "
                "FBIOBLANK will be disabled for this session and fallback methods will be used. "
                "Display OFF is implemented by drawing a full-screen black frame."
            ),
            flush=True,
        )
        self._write_status_file()

    def _draw_black_frame(self) -> bool:
        fb_name = Path(self.fbdev).name
        graphics_dir = Path("/sys/class/graphics") / fb_name
        width, height = _read_virtual_size(graphics_dir / "virtual_size") or (320, 240)
        bpp = _read_int_file(graphics_dir / "bits_per_pixel", 16)
        bytes_per_pixel = max(1, bpp // 8)
        payload_size = width * height * bytes_per_pixel

        try:
            with open(self.fbdev, "r+b", buffering=0) as fb:
                fb.seek(0)
                fb.write(b"\x00" * payload_size)
            self._black_fill_success_total += 1
            return True
        except Exception:
            self._black_fill_failures_total += 1
            return False

    def _toggle_via_fb_blank(self, target: int) -> bool:
        if not self._fb_blank_supported:
            return False
        try:
            with open(self.fbdev, "rb", buffering=0) as fb:
                fcntl.ioctl(fb.fileno(), FBIOBLANK, target)
            return True
        except OSError as exc:
            # Some framebuffer drivers (for example fbtft) don't support FBIOBLANK.
            if exc.errno == 22:
                self._fb_blank_supported = False
            raise

    def _toggle_via_sysfs_blank(self, screen_on: bool) -> bool:
        fb_name = Path(self.fbdev).name
        blank_path = Path("/sys/class/graphics") / fb_name / "blank"
        if not blank_path.exists():
            return False
        try:
            blank_path.write_text("0" if screen_on else "1", encoding="utf-8")
            return True
        except Exception:
            return False

    @staticmethod
    def _toggle_via_vcgencmd(screen_on: bool) -> bool:
        state = "1" if screen_on else "0"
        cmd = ["vcgencmd", "display_power", state]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return False
        return result.returncode == 0

    def toggle(self) -> None:
        """Toggle display state without stopping the rotator process.

        OFF draws a full-screen black framebuffer frame so the panel does not keep
        showing the last page. ON restores output using supported power backends.
        """
        target = FB_BLANK_POWERDOWN if self.screen_on else FB_BLANK_UNBLANK
        toggled = False
        method = "none"
        error = ""

        turning_on = not self.screen_on

        if turning_on and self._fb_blank_supported:
            try:
                toggled = self._toggle_via_fb_blank(target)
                if toggled:
                    method = "fb_blank"
                    self._fb_blank_success_total += 1
                    self._fb_blank_consecutive_failures = 0
            except Exception as exc:
                self._fb_blank_failures_total += 1
                self._fb_blank_consecutive_failures += 1
                error = str(exc)
                if self._fb_blank_consecutive_failures >= self._fb_blank_failure_threshold:
                    self._fb_blank_supported = False
                    self._fb_blank_disable_reason = (
                        f"{self._fb_blank_consecutive_failures} consecutive failures (last error: {error})"
                    )
                    print(
                        (
                            f"[rotator] FBIOBLANK disabled for this session on {self.fbdev}: "
                            f"{self._fb_blank_disable_reason}. Falling back to sysfs/vcgencmd only."
                        ),
                        flush=True,
                    )

        if turning_on and not toggled:
            toggled = self._toggle_via_sysfs_blank(screen_on=True)
            if toggled:
                method = "sysfs_blank"

        if turning_on and not toggled:
            toggled = self._toggle_via_vcgencmd(screen_on=True)
            if toggled:
                method = "vcgencmd"

        if not turning_on:
            toggled = self._draw_black_frame()
            method = "fb_black_frame"
            if not toggled:
                error = f"unable to write black frame to {self.fbdev}"

        self._last_toggle_method = method
        self._last_toggle_success = toggled
        self._last_toggle_error = error if not toggled else ""

        if toggled:
            self.screen_on = not self.screen_on
            print(f"[rotator] Screen {'ON' if self.screen_on else 'OFF'}", flush=True)
        else:
            print(
                f"[rotator] Screen toggle failed on {self.fbdev}: {error or 'no supported power control backend'}",
                flush=True,
            )

        self._maybe_log_power_summary()
        self._write_status_file()

    def _maybe_log_power_summary(self) -> None:
        now = time.monotonic()
        if (now - self._last_summary_ts) < self._power_summary_interval_secs:
            return

        self._last_summary_ts = now
        fb_blank_status = "enabled" if self._fb_blank_supported else "disabled"
        disable_reason = f" reason={self._fb_blank_disable_reason}" if self._fb_blank_disable_reason else ""
        print(
            (
                "[rotator] Power backend summary: "
                f"fb_blank={fb_blank_status} successes={self._fb_blank_success_total} "
                f"failures={self._fb_blank_failures_total} "
                f"consecutive_failures={self._fb_blank_consecutive_failures} "
                f"black_fill_successes={self._black_fill_success_total} "
                f"black_fill_failures={self._black_fill_failures_total}.{disable_reason}"
            ),
            flush=True,
        )

    def _write_status_file(self) -> None:
        if not self._status_file:
            return

        payload = {
            "timestamp": int(time.time()),
            "screen_on": self.screen_on,
            "last_toggle_method": self._last_toggle_method,
            "last_toggle_success": self._last_toggle_success,
            "last_toggle_error": self._last_toggle_error,
            "fb_blank_supported": self._fb_blank_supported,
            "fb_blank_disable_reason": self._fb_blank_disable_reason,
            "fb_blank_success_total": self._fb_blank_success_total,
            "fb_blank_failures_total": self._fb_blank_failures_total,
            "fb_blank_consecutive_failures": self._fb_blank_consecutive_failures,
            "black_fill_success_total": self._black_fill_success_total,
            "black_fill_failures_total": self._black_fill_failures_total,
        }

        try:
            status_path = Path(self._status_file)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(f"{json.dumps(payload, sort_keys=True)}\n", encoding="utf-8")
        except Exception:
            pass


def _parse_csv_patterns(raw: str) -> list[str]:
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def parse_exclude_patterns() -> tuple[list[str], bool]:
    raw = os.environ.get("ROTATOR_EXCLUDE_PATTERNS", "").strip()
    if raw:
        return _parse_csv_patterns(raw), True
    return DEFAULT_EXCLUDE_PATTERNS.copy(), False


def parse_include_patterns() -> list[str]:
    raw = os.environ.get("ROTATOR_INCLUDE_PATTERNS", "").strip()
    if not raw:
        return DEFAULT_INCLUDE_PATTERNS.copy()
    return _parse_csv_patterns(raw)


def _has_glob_tokens(pattern: str) -> bool:
    return any(token in pattern for token in "*?[]")


def _pattern_matches(path: Path, pattern: str, page_dir: Path, base_dir: Path) -> bool:
    relative_to_page_dir = path.relative_to(page_dir).as_posix()
    relative_to_base = path.relative_to(base_dir).as_posix()
    path_name = path.name

    if _has_glob_tokens(pattern):
        return (
            path.match(pattern)
            or Path(relative_to_page_dir).match(pattern)
            or Path(relative_to_base).match(pattern)
        )

    return pattern in {path_name, relative_to_page_dir, relative_to_base}


def _collect_page_candidates(page_dir: Path, page_globs: list[str]) -> list[Path]:
    seen: set[Path] = set()
    discovered: list[Path] = []
    for page_glob in page_globs:
        for path in sorted(page_dir.glob(page_glob)):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            discovered.append(path)
    return discovered


def _resolve_exact_pattern_candidate(page_dir: Path, pattern: str) -> Path | None:
    candidate = page_dir / pattern
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def discover_pages(base_dir: Path, list_pages: bool = False) -> list[str]:
    page_dir_raw = os.environ.get("ROTATOR_PAGES_DIR", DEFAULT_PAGES_DIR).strip() or DEFAULT_PAGES_DIR
    page_glob_raw = os.environ.get("ROTATOR_PAGE_GLOB", DEFAULT_PAGE_GLOB).strip() or DEFAULT_PAGE_GLOB
    page_globs = [entry.strip() for entry in page_glob_raw.split(",") if entry.strip()]
    excludes, exclude_is_user_configured = parse_exclude_patterns()
    includes = parse_include_patterns()

    page_dir = Path(page_dir_raw)
    if not page_dir.is_absolute():
        page_dir = base_dir / page_dir

    if not page_dir.exists():
        print(f"[rotator] Page directory does not exist: {page_dir}", flush=True)
        return []

    candidates = _collect_page_candidates(page_dir, page_globs)

    for pattern in includes:
        if _has_glob_tokens(pattern):
            continue
        exact = _resolve_exact_pattern_candidate(page_dir, pattern)
        if exact and exact not in candidates:
            candidates.append(exact)

    included: list[str] = []
    discovery_report: list[tuple[str, str]] = []
    user_excludes = excludes if exclude_is_user_configured else []
    default_excludes = DEFAULT_EXCLUDE_PATTERNS if not exclude_is_user_configured else []
    for path in sorted(candidates):
        relative = str(path.relative_to(base_dir))

        user_include_match = next((pat for pat in includes if _pattern_matches(path, pat, page_dir, base_dir)), None)
        user_exclude_match = next((pat for pat in user_excludes if _pattern_matches(path, pat, page_dir, base_dir)), None)
        default_exclude_match = next(
            (pat for pat in default_excludes if _pattern_matches(path, pat, page_dir, base_dir)),
            None,
        )

        if user_exclude_match:
            discovery_report.append((relative, f"excluded (user exclude: {user_exclude_match})"))
            continue
        if user_include_match:
            included.append(relative)
            discovery_report.append((relative, f"included (user include: {user_include_match})"))
            continue
        if default_exclude_match:
            discovery_report.append((relative, f"excluded (default exclude: {default_exclude_match})"))
            continue

        included.append(relative)
        discovery_report.append((relative, "included (matched discovery globs)"))

    print("[rotator] Discovery config:", flush=True)
    for item in DISCOVERY_CONFIG_DOCS:
        value = os.environ.get(item["env"], str(item["default"])).strip() or str(item["default"])
        print(f"[rotator]   {item['env']}={value} ({item['description']})", flush=True)

    print("[rotator] Discovery result:", flush=True)
    for script, status in discovery_report:
        print(f"[rotator]   {script}: {status}", flush=True)

    if list_pages:
        print("[rotator] --list-pages summary:", flush=True)
        for script, status in discovery_report:
            print(f"{script}\t{status}", flush=True)

    return included


def parse_pages(base_dir: Path, list_pages: bool = False) -> list[str]:
    # Backward-compatible manual override; otherwise scan a directory.
    raw = os.environ.get("ROTATOR_PAGES", "").strip()
    if raw:
        return [entry.strip() for entry in raw.split(",") if entry.strip()]
    return discover_pages(base_dir, list_pages=list_pages)


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


def parse_tap_debounce() -> float:
    raw = os.environ.get("ROTATOR_TAP_DEBOUNCE_SECS", str(TAP_DEBOUNCE_SECS)).strip()
    try:
        value = float(raw)
    except ValueError:
        value = TAP_DEBOUNCE_SECS
    return max(0.0, value)


def parse_quarantine_failure_threshold() -> int:
    raw = os.environ.get("ROTATOR_QUARANTINE_FAILURE_THRESHOLD", str(DEFAULT_QUARANTINE_FAILURE_THRESHOLD)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_QUARANTINE_FAILURE_THRESHOLD
    return max(1, value)


def parse_quarantine_cycles() -> int:
    raw = os.environ.get("ROTATOR_QUARANTINE_CYCLES", str(DEFAULT_QUARANTINE_CYCLES)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_QUARANTINE_CYCLES
    return max(1, value)


def parse_backoff_max_secs() -> int:
    raw = os.environ.get("ROTATOR_BACKOFF_MAX_SECS", str(DEFAULT_BACKOFF_MAX_SECS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_BACKOFF_MAX_SECS
    return max(1, value)


def calculate_backoff_secs(consecutive_failures: int, backoff_cap_secs: int) -> int:
    if consecutive_failures <= 0:
        return 0
    if consecutive_failures <= len(DEFAULT_BACKOFF_STEPS):
        return min(DEFAULT_BACKOFF_STEPS[consecutive_failures - 1], backoff_cap_secs)
    return min(DEFAULT_BACKOFF_STEPS[-1], backoff_cap_secs)


def format_failure_reason(returncode: int | None) -> str:
    if returncode is None:
        return "process stopped without a return code"
    if returncode < 0:
        return f"terminated by signal {-returncode}"
    return f"exit code {returncode}"


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


def _has_touch_abs(event_path: str) -> bool:
    caps_path = Path("/sys/class/input") / Path(event_path).name / "device" / "capabilities" / "abs"
    try:
        raw = caps_path.read_text(encoding="utf-8").strip()
        mask = int(raw, 16)
    except Exception:
        return False

    return bool(mask & (1 << ABS_X) or mask & (1 << ABS_MT_POSITION_X))


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

    device_touch_width, device_touch_min = detect_touch_width(device, touch_width)
    print(f"[rotator] Touch controls listening on {device} (width {device_touch_width})", flush=True)

    last_x = device_touch_min + (device_touch_width // 2)
    touch_down = False
    last_tap_ts = None
    last_emit = 0.0

    def emit_tap(tap_x: int, now: float) -> None:
        nonlocal last_tap_ts, last_emit
        relative_x = tap_x - device_touch_min
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
            cmd_q.put("PREV" if relative_x < (device_touch_width // 2) else "NEXT")
            last_emit = now
        last_tap_ts = now

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
                        emit_tap(last_x, time.monotonic())
                elif ev_type == EV_ABS and ev_code == ABS_MT_TRACKING_ID:
                    if ev_value == -1 and touch_down:
                        touch_down = False
                        emit_tap(last_x, time.monotonic())
                    elif ev_value >= 0:
                        touch_down = True
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

    pages = [
        resolved
        for resolved in (resolve_script(item, base_dir) for item in parse_pages(base_dir, list_pages=args.list_pages))
        if resolved is not None
    ]

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

        rotate_due = time.monotonic() + rotate_secs
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
            elif command == "NEXT":
                next_index = (index + 1) % len(pages)
                break
            elif command == "PREV":
                next_index = (index - 1) % len(pages)
                break

        stop_child(active_child)
        active_child = None

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


