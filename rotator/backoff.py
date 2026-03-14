"""Failure tracking helpers for the dashboard rotator."""

from __future__ import annotations

from rotator.defaults import DEFAULT_BACKOFF_STEPS


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
