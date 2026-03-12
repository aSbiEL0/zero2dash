#!/usr/bin/env python3
"""Sync image files from a shared Google Drive folder into LOCAL_PHOTOS_DIR."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2 import service_account

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _config import get_env, report_validation_errors

DEFAULT_ROOT = Path("~/zero2dash").expanduser()
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_STATE_PATH = DEFAULT_ROOT / "cache" / "drive_sync_state.json"
DEFAULT_RESIZE_SCRIPT = MODULE_DIR / "photo-resize.py"
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

@dataclass
class Config:
    folder_id: str
    service_account_json: Path
    local_photos_dir: Path
    state_path: Path
    resize_script: Path
    skip_resize: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync a shared Google Drive folder into LOCAL_PHOTOS_DIR.")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and exit")
    parser.add_argument("--list-remote", action="store_true", help="List the remote Drive images for GOOGLE_DRIVE_FOLDER_ID and exit")
    parser.add_argument("--debug", action="store_true", help="Print per-file diagnostic output")
    parser.add_argument("--skip-resize", action="store_true", help="Skip the follow-up resize step")
    return parser.parse_args()


def validate_config(skip_resize: bool) -> tuple[Config | None, list[str]]:
    errors: list[str] = []

    def record(name: str, *, default: Any = None, required: bool = False) -> Any:
        try:
            return get_env(name, default=default, required=required)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    folder_id = str(record("GOOGLE_DRIVE_FOLDER_ID", required=True))
    service_account_raw = str(record("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", default=str(DEFAULT_ROOT / "drive-service-account.json")))
    local_photos_raw = str(record("LOCAL_PHOTOS_DIR", default=str(DEFAULT_ROOT / "photos")))
    state_raw = str(record("GOOGLE_DRIVE_SYNC_STATE_PATH", default=str(DEFAULT_STATE_PATH)))
    resize_raw = str(record("PHOTO_RESIZE_SCRIPT", default=str(DEFAULT_RESIZE_SCRIPT)))

    service_account_json = Path(service_account_raw).expanduser()
    if not service_account_json.is_file():
        errors.append(f"GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON not found: {service_account_json}")

    config = Config(
        folder_id=folder_id,
        service_account_json=service_account_json,
        local_photos_dir=Path(local_photos_raw).expanduser(),
        state_path=Path(state_raw).expanduser(),
        resize_script=Path(resize_raw).expanduser(),
        skip_resize=skip_resize,
    )

    if errors:
        return None, errors
    return config, []


def load_config(skip_resize: bool) -> Config:
    load_dotenv(DEFAULT_ROOT / ".env")
    config, errors = validate_config(skip_resize)
    if errors:
        report_validation_errors("drive-sync.py", errors)
        raise ValueError("Invalid configuration")
    assert config is not None
    return config


def load_state(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def build_credentials(config: Config):
    creds = service_account.Credentials.from_service_account_file(
        str(config.service_account_json),
        scopes=DRIVE_SCOPES,
    )
    creds.refresh(Request())
    return creds


def drive_json(creds, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    creds.refresh(Request())
    url = f"https://www.googleapis.com/drive/v3/{endpoint}?{urlencode(params)}"
    req = UrlRequest(url, headers={"Authorization": f"Bearer {creds.token}"})
    try:
        with urlopen(req, timeout=30) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Google Drive API request failed ({exc.code} {exc.reason}): {body}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Google Drive API response must be a JSON object")
    return payload


def list_folder_images(creds, folder_id: str) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    page_token = ""
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false and mimeType contains 'image/'",
            "fields": "nextPageToken,files(id,name,mimeType,modifiedTime)",
            "pageSize": "1000",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        payload = drive_json(creds, "files", params)
        files = payload.get("files", [])
        if not isinstance(files, list):
            raise ValueError("Google Drive API response field 'files' must be a list")
        for item in files:
            if isinstance(item, dict):
                images.append({
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or "image"),
                    "mimeType": str(item.get("mimeType") or "image/jpeg"),
                    "modifiedTime": str(item.get("modifiedTime") or ""),
                })
        page_token = str(payload.get("nextPageToken") or "")
        if not page_token:
            break
    return [item for item in images if item["id"]]


def print_remote_inventory(folder_id: str, items: list[dict[str, str]], *, debug: bool = False) -> None:
    print(f"[drive-sync.py] Drive folder {folder_id}: {len(items)} image file(s) discovered.")
    for item in items:
        if debug:
            print(
                f"  - id={item['id']} name={item['name']} mimeType={item['mimeType']} modifiedTime={item['modifiedTime']}"
            )
        else:
            print(f"  - {item['name']} ({item['id']})")


def safe_stem(name: str) -> str:
    stem = Path(name).stem or "image"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "image"


def suffix_for_item(item: dict[str, str]) -> str:
    suffix = Path(item["name"]).suffix.lower()
    if suffix in ALLOWED_SUFFIXES:
        return suffix
    guessed = (mimetypes.guess_extension(item["mimeType"]) or ".jpg").lower()
    return ".jpg" if guessed == ".jpe" else guessed


def local_path_for_item(local_dir: Path, item: dict[str, str]) -> Path:
    return local_dir / f"drive-{item['id']}-{safe_stem(item['name'])}{suffix_for_item(item)}"


def download_file(creds, file_id: str, target: Path) -> None:
    creds.refresh(Request())
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"
    req = UrlRequest(url, headers={"Authorization": f"Bearer {creds.token}"})
    with urlopen(req, timeout=60) as response:  # nosec B310
        data = response.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def run_resize(config: Config) -> None:
    if config.skip_resize:
        print("[drive-sync.py] Resize step skipped (--skip-resize).")
        return
    if not config.resize_script.is_file():
        print(f"[drive-sync.py] Resize script not found: {config.resize_script}; skipping resize step.")
        return
    result = subprocess.run([sys.executable, str(config.resize_script)], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Resize step failed with exit code {result.returncode}")


def sync_drive(config: Config, *, debug: bool = False) -> None:
    creds = build_credentials(config)
    items = list_folder_images(creds, config.folder_id)
    print(f"[drive-sync.py] Syncing Drive folder {config.folder_id} into {config.local_photos_dir}")
    if debug:
        print_remote_inventory(config.folder_id, items, debug=True)
    config.local_photos_dir.mkdir(parents=True, exist_ok=True)

    state = load_state(config.state_path)
    next_state: dict[str, dict[str, str]] = {}
    downloaded = 0
    skipped = 0
    removed = 0

    for item in items:
        target = local_path_for_item(config.local_photos_dir, item)
        previous = state.get(item["id"], {})
        previous_name = previous.get("local_name", "")
        previous_target = config.local_photos_dir / previous_name if previous_name else None
        if previous_target and previous_target != target and previous_target.exists() and previous_target.name.startswith("drive-"):
            previous_target.unlink()
        if previous.get("modifiedTime") == item["modifiedTime"] and target.exists():
            skipped += 1
            if debug:
                print(f"[drive-sync.py] SKIP   id={item['id']} name={item['name']} target={target.name}")
        else:
            download_file(creds, item["id"], target)
            downloaded += 1
            if debug:
                print(f"[drive-sync.py] FETCH  id={item['id']} name={item['name']} target={target.name}")
        next_state[item["id"]] = {
            "modifiedTime": item["modifiedTime"],
            "local_name": target.name,
            "name": item["name"],
            "mimeType": item["mimeType"],
        }

    stale_ids = set(state) - set(next_state)
    for stale_id in stale_ids:
        stale_name = state.get(stale_id, {}).get("local_name", "")
        stale_path = config.local_photos_dir / stale_name if stale_name else None
        if stale_path and stale_path.exists() and stale_path.name.startswith("drive-"):
            stale_path.unlink()
            removed += 1
            if debug:
                print(f"[drive-sync.py] REMOVE id={stale_id} target={stale_path.name}")

    save_state(config.state_path, next_state)
    print(f"[drive-sync.py] Synced {len(items)} images: downloaded={downloaded}, skipped={skipped}, removed={removed}.")
    run_resize(config)


def main() -> int:
    args = parse_args()
    try:
        config = load_config(skip_resize=args.skip_resize)
    except ValueError:
        return 1

    if args.check_config:
        print("[drive-sync.py] Configuration check passed.")
        return 0

    creds = build_credentials(config)
    items = list_folder_images(creds, config.folder_id)
    if args.list_remote:
        print_remote_inventory(config.folder_id, items, debug=args.debug)
        return 0

    sync_drive(config, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


