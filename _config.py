#!/usr/bin/env python3
"""Shared environment/config helpers for dashboard scripts."""

from __future__ import annotations

import os
from typing import Any, Callable

Validator = Callable[[str], Any]


def get_env(
    name: str,
    default: Any = None,
    required: bool = False,
    validator: Validator | None = None,
) -> Any:
    """Read and validate an environment variable.

    Args:
        name: Environment variable name.
        default: Value returned when env is unset/blank and not required.
        required: When True, env must be set to a non-empty value.
        validator: Optional callable to transform/validate the raw string value.

    Raises:
        ValueError: If required value is missing or validator rejects the value.
    """

    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        if required:
            raise ValueError(f"{name} is required but not set.")
        return default

    value = raw_value.strip()
    if validator is None:
        return value

    try:
        return validator(value)
    except ValueError as exc:
        raise ValueError(f"{name} is invalid: {exc}") from exc
    except Exception as exc:  # defensive: normalize unknown validator errors
        raise ValueError(f"{name} is invalid: {exc}") from exc


def report_validation_errors(script_name: str, errors: list[str]) -> None:
    """Print a single structured validation report."""
    print(f"[{script_name}] Configuration check failed ({len(errors)} issue{'s' if len(errors) != 1 else ''}):")
    for issue in errors:
        print(f"  - {issue}")
