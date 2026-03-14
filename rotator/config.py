"""Environment parsing helpers for the dashboard rotator."""

from __future__ import annotations

import os

from rotator.defaults import (
    DEFAULT_BACKOFF_MAX_SECS,
    DEFAULT_QUARANTINE_CYCLES,
    DEFAULT_QUARANTINE_FAILURE_THRESHOLD,
    DEFAULT_ROTATE_SECS,
    DEFAULT_WIDTH,
    MIN_DWELL_SECS,
    TAP_DEBOUNCE_SECS,
)


def parse_rotate_secs() -> int:
    raw = os.environ.get("ROTATOR_SECS", str(DEFAULT_ROTATE_SECS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_ROTATE_SECS
    return max(MIN_DWELL_SECS, value)


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
