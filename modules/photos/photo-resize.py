#!/usr/bin/env python3
"""Resize changed images in LOCAL_PHOTOS_DIR to 50% of their current dimensions."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from PIL import Image, ImageOps

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _config import get_env, report_validation_errors

DEFAULT_ROOT = Path("~/zero2dash").expanduser()
DEFAULT_STATE_PATH = DEFAULT_ROOT / "cache" / "photo_resize_state.json"
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
RESIZE_SCALE = 0.5

@dataclass
class Config:
    local_photos_dir: Path
    state_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resize changed photos in LOCAL_PHOTOS_DIR by 50%.")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and exit")
    return parser.parse_args()


def validate_config() -> tuple[Config | None, list[str]]:
    errors: list[str] = []

    def record(name: str, *, default: Any = None, required: bool = False) -> Any:
        try:
            return get_env(name, default=default, required=required)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    local_photos_raw = str(record("LOCAL_PHOTOS_DIR", default=str(DEFAULT_ROOT / "photos")))
    state_raw = str(record("PHOTO_RESIZE_STATE_PATH", default=str(DEFAULT_STATE_PATH)))

    config = Config(
        local_photos_dir=Path(local_photos_raw).expanduser(),
        state_path=Path(state_raw).expanduser(),
    )
    if errors:
        return None, errors
    return config, []


def load_state(path: Path) -> dict[str, dict[str, int]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict[str, dict[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def iter_images(local_photos_dir: Path) -> list[Path]:
    if not local_photos_dir.exists():
        return []
    return sorted(
        path
        for path in local_photos_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES
    )


def resize_in_place(path: Path) -> None:
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        width = max(1, int(round(image.width * RESIZE_SCALE)))
        height = max(1, int(round(image.height * RESIZE_SCALE)))
        resized = image.resize((width, height), Image.Resampling.LANCZOS)
        save_kwargs: dict[str, Any] = {}
        suffix = path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            if resized.mode != "RGB":
                resized = resized.convert("RGB")
            save_kwargs = {"quality": 90, "optimize": True}
        elif suffix == ".png":
            save_kwargs = {"optimize": True}
        resized.save(path, **save_kwargs)


def main() -> int:
    args = parse_args()
    load_dotenv(DEFAULT_ROOT / ".env")
    config, errors = validate_config()
    if errors:
        report_validation_errors("photo-resize.py", errors)
        return 1
    assert config is not None

    if args.check_config:
        print("[photo-resize.py] Configuration check passed.")
        return 0

    config.local_photos_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(config.state_path)
    next_state: dict[str, dict[str, int]] = {}
    processed = 0
    skipped = 0

    for image_path in iter_images(config.local_photos_dir):
        stat = image_path.stat()
        key = str(image_path.relative_to(config.local_photos_dir))
        current = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if state.get(key) == current:
            next_state[key] = current
            skipped += 1
            continue
        resize_in_place(image_path)
        updated = image_path.stat()
        next_state[key] = {"size": updated.st_size, "mtime_ns": updated.st_mtime_ns}
        processed += 1

    save_state(config.state_path, next_state)
    print(f"[photo-resize.py] Processed={processed}, skipped={skipped}, total={processed + skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

