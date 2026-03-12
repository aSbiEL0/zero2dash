#!/usr/bin/env python3
"""Compatibility entrypoint for the pihole display module."""

from __future__ import annotations

import runpy
from pathlib import Path

LEGACY_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "piholestats_manual.py"


def main() -> int:
    runpy.run_path(str(LEGACY_SCRIPT), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
