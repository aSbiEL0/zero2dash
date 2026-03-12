#!/usr/bin/env python3
"""Compatibility entrypoint for the moved photos module script."""

from __future__ import annotations

import runpy
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "modules" / "photos" / "photos-shuffle.py"
runpy.run_path(str(TARGET), run_name="__main__")
