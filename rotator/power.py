"""Framebuffer power control helpers for the dashboard rotator."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time
from pathlib import Path


DEFAULT_FB_BLANK_FAILURE_THRESHOLD = 3
DEFAULT_POWER_SUMMARY_INTERVAL_SECS = 300
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
