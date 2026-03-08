#!/usr/bin/env python3
"""
photos-shuffle.py

One-shot photo renderer for a 320x240 framebuffer page.

Requirements (pip): Pillow, python-dotenv, google-auth, google-auth-oauthlib,
google-api-python-client.

Configuration (.env):
- Optional: LOCAL_PHOTOS_DIR, GOOGLE_PHOTOS_ALBUM_ID, GOOGLE_PHOTOS_CLIENT_SECRETS_PATH,
  GOOGLE_TOKEN_PATH_PHOTOS, FB_DEVICE, WIDTH, HEIGHT, CACHE_DIR, FALLBACK_IMAGE, LOGO_PATH
- Optional OAuth alternative: GOOGLE_PHOTOS_CLIENT_ID and GOOGLE_PHOTOS_CLIENT_SECRET
  (used when GOOGLE_PHOTOS_CLIENT_SECRETS_PATH file is not present).

OAuth setup:
- Put OAuth client secrets JSON at ~/zero2dash/client_secret.json (or override
  with GOOGLE_PHOTOS_CLIENT_SECRETS_PATH).
- Token path defaults to ~/zero2dash/token_photos.json so it does not
  conflict with calendar scripts that use token.json (override with
  GOOGLE_TOKEN_PATH_PHOTOS if needed).
- On first run, if token is missing/invalid and refresh is unavailable, the
  script starts a local OAuth flow and prints instructions to complete login.
- Loopback OAuth only: complete the browser sign-in on the same machine as the
  script, or use SSH port forwarding to forward the callback port from the Pi.
- Use a Desktop OAuth client. If the Google app is in testing, add your
  account as a test user before first run.
- Since 31 March 2025, Google Photos Library API read access is limited to app-created
  albums and media items. Personal/shared albums should use LOCAL_PHOTOS_DIR,
  optionally populated by Google Drive sync.

Fallback:
- Preferred source is LOCAL_PHOTOS_DIR (default: ~/zero2dash/photos). If it is empty, the
  script can still try Google Photos when configured, then CACHE_DIR, then FALLBACK_IMAGE.
- Ensure local fallback image exists at ~/zero2dash/images/photos-fallback.png
  (or override with FALLBACK_IMAGE).
"""

from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from _config import get_env, report_validation_errors

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from PIL import Image, ImageEnhance

SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata"]
DEFAULT_ROOT = Path("~/zero2dash").expanduser()
TEST_OUTPUT = Path("/tmp/photos-shuffle-test.png")
LOGO_WIDTH_RATIO = 0.14
LOGO_PADDING_RATIO = 0.03
BRIGHTNESS_FACTOR = 0.75


@dataclass
class Config:
    local_photos_dir: Path
    album_id: str
    client_secrets_path: Path
    client_id: str
    client_secret: str
    token_path: Path
    fb_device: str
    width: int
    height: int
    cache_dir: Path
    fallback_image: Path
    logo_path: Path
    oauth_port: int
    oauth_open_browser: bool


def _normalize_scopes(raw_scopes: Any) -> set[str]:
    if isinstance(raw_scopes, str):
        return {scope for scope in raw_scopes.replace(",", " ").split() if scope}
    if isinstance(raw_scopes, (list, tuple, set)):
        return {str(scope) for scope in raw_scopes if scope}
    return set()


def _is_token_compatible_with_photos(token_payload: dict[str, Any]) -> bool:
    token_scopes = _normalize_scopes(token_payload.get("scopes") or token_payload.get("scope"))
    if not token_scopes:
        return True
    return set(SCOPES).issubset(token_scopes)


class Log:
    def __init__(self, debug: bool = False) -> None:
        self.debug_enabled = debug

    def info(self, message: str) -> None:
        print(message)

    def debug(self, message: str) -> None:
        if self.debug_enabled:
            print(f"[debug] {message}")


def expected_redirect_uri(oauth_port: int) -> str:
    return f"http://localhost:{oauth_port}/"


def build_client_config(client_id: str, client_secret: str, oauth_port: int) -> dict[str, Any]:
    redirect_uri = expected_redirect_uri(oauth_port)
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [
                "http://localhost",
                "http://localhost/",
                f"http://localhost:{oauth_port}",
                redirect_uri,
                "http://127.0.0.1",
                "http://127.0.0.1/",
                f"http://127.0.0.1:{oauth_port}",
                redirect_uri.replace("localhost", "127.0.0.1", 1),
            ],
        }
    }


def loopback_oauth_guidance(oauth_port: int) -> list[str]:
    redirect_uri = expected_redirect_uri(oauth_port)
    return [
        "Loopback OAuth only: complete Google sign-in on the same machine that is running this script.",
        f"For a headless Pi, forward the callback port first: ssh -L {oauth_port}:localhost:{oauth_port} <user>@<pi-host>",
        "Use a Desktop OAuth client. If your Google app is in testing, add your account as a test user.",
        f"Expected redirect URI: {redirect_uri}",
    ]


def _as_int(name: str, value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"expected integer, got {value!r}") from exc


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def validate_config() -> tuple[Config | None, list[str]]:
    errors: list[str] = []

    def record(name: str, *, default: Any = None, required: bool = False, validator: Any = None) -> Any:
        try:
            return get_env(name, default=default, required=required, validator=validator)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    local_photos_raw = record("LOCAL_PHOTOS_DIR", default=str(DEFAULT_ROOT / "photos"))
    album_id = record("GOOGLE_PHOTOS_ALBUM_ID", default="")
    client_secrets_raw = record("GOOGLE_PHOTOS_CLIENT_SECRETS_PATH", default=str(DEFAULT_ROOT / "client_secret.json"))

    client_id = record("GOOGLE_PHOTOS_CLIENT_ID") or record("GOOGLE_CLIENT_ID") or ""
    client_secret = record("GOOGLE_PHOTOS_CLIENT_SECRET") or record("GOOGLE_CLIENT_SECRET") or ""

    token_raw = record("GOOGLE_TOKEN_PATH_PHOTOS", default=str(DEFAULT_ROOT / "token_photos.json"))
    fb_device = record("FB_DEVICE", default="/dev/fb1")
    width = record("WIDTH", default=320, validator=lambda v: _as_int("WIDTH", v))
    height = record("HEIGHT", default=240, validator=lambda v: _as_int("HEIGHT", v))
    cache_raw = record("CACHE_DIR", default=str(DEFAULT_ROOT / "cache" / "google_photos"))
    fallback_raw = record("FALLBACK_IMAGE", default=str(DEFAULT_ROOT / "images" / "photos-fallback.png"))
    logo_raw = record("LOGO_PATH", default="/images/goo-photos-icon.png")
    oauth_port = record("OAUTH_PORT", default=8080, validator=lambda v: _as_int("OAUTH_PORT", v))
    oauth_open_browser = record("OAUTH_OPEN_BROWSER", default=False, validator=_as_bool)

    if isinstance(width, int) and width <= 0:
        errors.append("WIDTH is invalid: must be greater than 0")
    if isinstance(height, int) and height <= 0:
        errors.append("HEIGHT is invalid: must be greater than 0")
    if isinstance(oauth_port, int) and oauth_port <= 0:
        errors.append("OAUTH_PORT is invalid: must be greater than 0")

    fallback_image = Path(str(fallback_raw)).expanduser()
    if not fallback_image.exists():
        errors.append(f"FALLBACK_IMAGE not found: {fallback_image}")

    config = Config(
        local_photos_dir=Path(str(local_photos_raw)).expanduser(),
        album_id=str(album_id),
        client_secrets_path=Path(str(client_secrets_raw)).expanduser(),
        client_id=str(client_id),
        client_secret=str(client_secret),
        token_path=Path(str(token_raw)).expanduser(),
        fb_device=str(fb_device),
        width=int(width),
        height=int(height),
        cache_dir=Path(str(cache_raw)).expanduser(),
        fallback_image=fallback_image,
        logo_path=Path(str(logo_raw)).expanduser(),
        oauth_port=int(oauth_port),
        oauth_open_browser=bool(oauth_open_browser),
    )

    calendar_default_token = (DEFAULT_ROOT / "token.json").resolve()
    if config.album_id and config.token_path.resolve() == calendar_default_token:
        errors.append(
            "GOOGLE_TOKEN_PATH_PHOTOS points to token.json, which is reserved for calendash-api.py. "
            "Use a separate photos token path (default: ~/zero2dash/token_photos.json)."
        )

    if config.album_id and not config.client_secrets_path.exists() and not (config.client_id and config.client_secret):
        errors.append(
            f"Google Photos OAuth credentials are required: set GOOGLE_PHOTOS_CLIENT_SECRETS_PATH to an existing file "
            f"or provide GOOGLE_PHOTOS_CLIENT_ID + GOOGLE_PHOTOS_CLIENT_SECRET (checked path: {config.client_secrets_path})."
        )

    if errors:
        return None, errors
    return config, []


def load_config() -> Config:
    load_dotenv(DEFAULT_ROOT / ".env")
    config, errors = validate_config()
    if errors:
        report_validation_errors("photos-shuffle.py", errors)
        raise ValueError("Invalid configuration")
    assert config is not None
    return config


def authenticate(config: Config, log: Log) -> Credentials:
    creds: Credentials | None = None

    calendar_default_token = (DEFAULT_ROOT / "token.json").resolve()
    if config.album_id and config.token_path.resolve() == calendar_default_token:
        raise ValueError(
            "GOOGLE_TOKEN_PATH_PHOTOS points to token.json, which is reserved for calendash-api.py. "
            "Use a separate photos token path (default: ~/zero2dash/token_photos.json)."
        )

    if config.token_path.exists():
        try:
            payload = json.loads(config.token_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.info(f"Existing token at {config.token_path} is invalid ({exc}); re-authenticating")
            payload = None

        if payload and not _is_token_compatible_with_photos(payload):
            log.info(
                f"Token at {config.token_path} does not include required Google Photos scope {SCOPES[0]}; re-authenticating"
            )
        else:
            try:
                creds = Credentials.from_authorized_user_file(str(config.token_path), SCOPES)
            except Exception as exc:
                log.info(f"Existing token at {config.token_path} is invalid ({exc}); re-authenticating")
                creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        log.debug("Refreshing existing Google OAuth token")
        try:
            creds.refresh(Request())
        except Exception as exc:
            log.info(f"Token refresh failed ({exc}); starting OAuth flow")
            creds = None

    if not creds or not creds.valid:
        log.info("No valid Google token found; starting OAuth local server flow.")
        log.info(
            "Complete Google sign-in on this machine, or use SSH port forwarding for the loopback callback."
        )
        if config.client_secrets_path.exists():
            flow = InstalledAppFlow.from_client_secrets_file(str(config.client_secrets_path), SCOPES)
        elif config.client_id and config.client_secret:
            flow = InstalledAppFlow.from_client_config(
                build_client_config(config.client_id, config.client_secret, config.oauth_port),
                SCOPES,
            )
        else:
            raise FileNotFoundError(
                f"Client secret not found: {config.client_secrets_path}; set GOOGLE_PHOTOS_CLIENT_SECRETS_PATH "
                "or provide GOOGLE_PHOTOS_CLIENT_ID + GOOGLE_PHOTOS_CLIENT_SECRET in .env"
            )
        try:
            creds = flow.run_local_server(
                port=config.oauth_port,
                prompt="consent",
                authorization_prompt_message="Open this URL in your browser to authorize Google Photos access: {url}",
                open_browser=config.oauth_open_browser,
                redirect_uri_trailing_slash=True,
            )
        except Exception as exc:
            exc_text = str(exc).lower()
            if "redirect_uri_mismatch" in exc_text:
                log.info(f"OAuth redirect mismatch. Expected redirect URI: {expected_redirect_uri(config.oauth_port)}")
            if any(tag in exc_text for tag in ["access blocked", "app is blocked", "app restricted", "invalid_client"]):
                log.info("Google blocked this OAuth client for Photos. Use a dedicated Desktop OAuth client and add your account as a test user.")
                log.info("Set GOOGLE_PHOTOS_CLIENT_ID / GOOGLE_PHOTOS_CLIENT_SECRET (or GOOGLE_PHOTOS_CLIENT_SECRETS_PATH) in .env.")
            for message in loopback_oauth_guidance(config.oauth_port):
                log.info(message)
            raise RuntimeError("Loopback OAuth setup failed") from exc

    config.token_path.parent.mkdir(parents=True, exist_ok=True)
    config.token_path.write_text(creds.to_json(), encoding="utf-8")
    log.debug(f"Saved OAuth token to {config.token_path}")
    return creds


def _photos_api_json(creds: Credentials, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
    from urllib.request import Request as UrlRequest, urlopen

    url = f"https://photoslibrary.googleapis.com/v1/{endpoint}"
    payload = json.dumps(body).encode("utf-8")
    request = UrlRequest(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:  # nosec B310
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = _describe_google_api_error(exc)
        if detail:
            raise RuntimeError(detail) from exc
        raise
    if not isinstance(data, dict):
        raise ValueError("Google Photos API response must be a JSON object")
    return data


def _describe_google_api_error(exc: HTTPError) -> str:
    try:
        raw_body = exc.read()
    except Exception:
        raw_body = b""

    body_text = raw_body.decode("utf-8", "replace").strip() if raw_body else ""
    try:
        payload = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        payload = {}

    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return f"Google Photos API request failed ({exc.code} {exc.reason})"

    message = str(error.get("message") or f"Google Photos API request failed ({exc.code} {exc.reason})").strip()
    lowered = message.lower()
    if "insufficient authentication scopes" in lowered:
        return (
            "Google Photos Library API removed photoslibrary.readonly on 31 March 2025. "
            "This script now only works with app-created albums/media using "
            "photoslibrary.readonly.appcreateddata. Re-authorise with the new scope, "
            "or populate CACHE_DIR from another source for personal/shared albums."
        )

    details = error.get("details")
    if not isinstance(details, list):
        return message

    for detail in details:
        if not isinstance(detail, dict):
            continue
        metadata = detail.get("metadata")
        if detail.get("reason") == "SERVICE_DISABLED" and isinstance(metadata, dict):
            activation_url = metadata.get("activationUrl")
            consumer = metadata.get("consumer")
            if activation_url and consumer:
                return f"{message} Enable Photos Library API for {consumer}: {activation_url}"
            if activation_url:
                return f"{message} Enable Photos Library API here: {activation_url}"

    return message


def list_album_images(creds: Credentials, album_id: str, log: Log) -> list[dict[str, Any]]:
    return _list_album_images(lambda body: _photos_api_json(creds, "mediaItems:search", body), album_id, log)


def _list_album_images_from_service(service: Any, album_id: str, log: Log) -> list[dict[str, Any]]:
    return _list_album_images(lambda body: service.mediaItems().search(body=body).execute(), album_id, log)


def _list_album_images(fetch_page: Any, album_id: str, log: Log) -> list[dict[str, Any]]:
    if not album_id:
        raise ValueError("album_id is required")

    page_token: str | None = None
    images: list[dict[str, Any]] = []
    page_count = 0

    while True:
        page_count += 1
        body: dict[str, Any] = {"albumId": album_id, "pageSize": 100}
        if page_token:
            body["pageToken"] = page_token

        response = fetch_page(body)
        if not isinstance(response, dict):
            raise ValueError("Google Photos API response must be a JSON object")

        media_items = response.get("mediaItems", [])
        if media_items is None:
            media_items = []
        if not isinstance(media_items, list):
            raise ValueError("Google Photos API response field 'mediaItems' must be a list when present")

        for item in media_items:
            if not isinstance(item, dict):
                continue
            mime = (item.get("mimeType") or "").lower()
            if mime.startswith("image/"):
                images.append(item)

        page_token = response.get("nextPageToken")
        if page_token is not None and not isinstance(page_token, str):
            raise ValueError("Google Photos API response field 'nextPageToken' must be a string when present")
        if not page_token:
            break

    log.debug(f"Album returned {len(images)} image media items across {page_count} pages")
    return images

def smoke_check_list_fetch(log: Log) -> None:
    class _Request:
        def __init__(self, response: dict[str, Any]):
            self._response = response

        def execute(self) -> dict[str, Any]:
            return self._response

    class _MediaItems:
        def __init__(self, pages: list[dict[str, Any]], calls: list[dict[str, Any]]):
            self._pages = pages
            self._calls = calls
            self._index = 0

        def search(self, body: dict[str, Any]) -> _Request:
            self._calls.append(body)
            if self._index >= len(self._pages):
                raise AssertionError("search called more times than available pages")
            response = self._pages[self._index]
            self._index += 1
            return _Request(response)

    class _Service:
        def __init__(self, pages: list[dict[str, Any]], calls: list[dict[str, Any]]):
            self._media_items = _MediaItems(pages, calls)

        def mediaItems(self) -> _MediaItems:
            return self._media_items

    calls: list[dict[str, Any]] = []
    pages = [
        {
            "mediaItems": [
                {"id": "a", "mimeType": "image/jpeg"},
                {"id": "b", "mimeType": "video/mp4"},
            ],
            "nextPageToken": "token-2",
        },
        {
            "mediaItems": [{"id": "c", "mimeType": "image/png"}],
        },
    ]
    images = _list_album_images_from_service(_Service(pages, calls), "album-123", log)

    if [item.get("id") for item in images] != ["a", "c"]:
        raise AssertionError("Smoke check failed: expected image filtering and aggregation across pages")
    if len(calls) != 2:
        raise AssertionError("Smoke check failed: expected two paginated search calls")
    if calls[0].get("albumId") != "album-123" or calls[1].get("albumId") != "album-123":
        raise AssertionError("Smoke check failed: expected albumId in every search request")
    if "pageToken" in calls[0]:
        raise AssertionError("Smoke check failed: first request should not include pageToken")
    if calls[1].get("pageToken") != "token-2":
        raise AssertionError("Smoke check failed: second request must use nextPageToken from previous page")

    log.info("List fetch smoke check passed")


def extension_for_item(item: dict[str, Any]) -> str:
    mime = (item.get("mimeType") or "").lower()
    if mime == "image/png":
        return ".png"
    if mime == "image/webp":
        return ".webp"
    return ".jpg"


def cache_path_for_item(cache_dir: Path, item: dict[str, Any]) -> Path:
    media_id = (item.get("id") or "unknown").strip().replace("/", "_")
    return cache_dir / f"{media_id}{extension_for_item(item)}"


def download_to_cache(creds: Credentials, item: dict[str, Any], cache_path: Path, config: Config, log: Log) -> None:
    base_url = item.get("baseUrl")
    if not base_url:
        raise ValueError("mediaItem missing baseUrl")

    sized_url = f"{base_url}=w{config.width * 2}-h{config.height * 2}"
    from urllib.request import Request as UrlRequest, urlopen

    req = UrlRequest(sized_url, headers={"Authorization": f"Bearer {creds.token}"})
    with urlopen(req, timeout=20) as resp:  # nosec B310
        data = resp.read()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    log.debug(f"Cached image: {cache_path}")


def list_cached_images(cache_dir: Path) -> list[Path]:
    if not cache_dir.exists():
        return []
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    return [p for p in cache_dir.iterdir() if p.is_file() and p.suffix.lower() in allowed]


def center_crop_fill(img: Image.Image, width: int, height: int) -> Image.Image:
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    resized = img.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))), Image.Resampling.LANCZOS)

    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def composite_frame(photo_path: Path, logo_path: Path, width: int, height: int) -> Image.Image:
    with Image.open(photo_path) as raw_photo:
        photo = center_crop_fill(raw_photo.convert("RGB"), width, height)

    photo = ImageEnhance.Brightness(photo).enhance(BRIGHTNESS_FACTOR)

    if logo_path.exists():
        with Image.open(logo_path) as logo_raw:
            logo = logo_raw.convert("RGBA")
            logo_width = max(1, int(width * LOGO_WIDTH_RATIO))
            logo_height = max(1, int(logo.height * (logo_width / max(1, logo.width))))
            logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)

            padding = max(1, int(width * LOGO_PADDING_RATIO))
            x = max(0, width - logo.width - padding)
            y = padding

            frame = photo.convert("RGBA")
            frame.alpha_composite(logo, (x, y))
            return frame.convert("RGB")

    return photo


def rgb888_to_rgb565_bytes(img: Image.Image) -> bytes:
    rgb = img.convert("RGB").tobytes()
    out = bytearray((len(rgb) // 3) * 2)
    j = 0
    for i in range(0, len(rgb), 3):
        r = rgb[i]
        g = rgb[i + 1]
        b = rgb[i + 2]
        value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[j] = value & 0xFF
        out[j + 1] = (value >> 8) & 0xFF
        j += 2
    return bytes(out)


def write_framebuffer(img: Image.Image, fb_device: str, width: int, height: int) -> None:
    payload = rgb888_to_rgb565_bytes(img)
    expected = width * height * 2
    if len(payload) != expected:
        raise ValueError(f"RGB565 payload size mismatch: {len(payload)} != {expected}")

    with open(fb_device, "r+b", buffering=0) as fb:
        fb.seek(0)
        fb.write(payload)


def choose_local_image(config: Config, log: Log) -> Path:
    local_images = list_cached_images(config.local_photos_dir)
    if not local_images:
        raise RuntimeError(f"Local photos directory empty: {config.local_photos_dir}")
    chosen = random.choice(local_images)
    log.info(f"LOCAL: selected {chosen.name}")
    return chosen

def choose_online_image(config: Config, log: Log) -> Path:
    if not config.album_id:
        raise RuntimeError("GOOGLE_PHOTOS_ALBUM_ID not configured")

    creds = authenticate(config, log)
    items = list_album_images(creds, config.album_id, log)
    if not items:
        raise RuntimeError("No image media items found in album")

    random.shuffle(items)
    for item in items:
        media_id = item.get("id", "unknown")
        cache_path = cache_path_for_item(config.cache_dir, item)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            log.info(f"ONLINE: cache hit for {media_id}")
            return cache_path

        log.info(f"ONLINE: cache miss for {media_id}; downloading")
        try:
            download_to_cache(creds, item, cache_path, config, log)
            return cache_path
        except Exception as exc:
            log.debug(f"Download failed for {media_id}: {exc}")
            continue

    raise RuntimeError("Unable to fetch any album image")


def choose_offline_image(config: Config, log: Log) -> Path:
    cached = list_cached_images(config.cache_dir)
    if not cached:
        raise RuntimeError("Offline cache empty")
    chosen = random.choice(cached)
    log.info(f"OFFLINE: selected cached image {chosen.name}")
    return chosen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render one random Google Photos album image to framebuffer.")
    parser.add_argument("--test", action="store_true", help="Render to /tmp/photos-shuffle-test.png instead of framebuffer")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logs")
    parser.add_argument("--check-config", action="store_true", help="Validate env configuration and exit")
    parser.add_argument("--auth-only", action="store_true", help="Run OAuth/token setup only and exit")
    parser.add_argument("--smoke-list-fetch", action="store_true", help="Run paginated list fetch smoke check and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log = Log(debug=args.debug)

    if args.smoke_list_fetch:
        try:
            smoke_check_list_fetch(log)
            return 0
        except Exception as exc:
            print(f"List fetch smoke check failed: {exc}")
            return 1

    load_dotenv(DEFAULT_ROOT / ".env")
    config, errors = validate_config()
    if errors:
        report_validation_errors("photos-shuffle.py", errors)
        return 1
    assert config is not None

    if args.check_config:
        print("[photos-shuffle.py] Configuration check passed.")
        return 0

    if args.auth_only:
        if not config.album_id:
            print("[photos-shuffle.py] No Google Photos album configured; auth check skipped.")
            return 0
        authenticate(config, log)
        print("[photos-shuffle.py] Authentication check passed.")
        return 0

    source_image: Path | None = None
    try:
        source_image = choose_local_image(config, log)
    except Exception as local_exc:
        log.info(f"Local photos unavailable ({local_exc}); trying online source")
        try:
            source_image = choose_online_image(config, log)
        except Exception as exc:
            log.info(f"Online unavailable ({exc}); trying offline cache")
            try:
                source_image = choose_offline_image(config, log)
            except Exception as off_exc:
                log.info(f"Offline cache unavailable ({off_exc}); using fallback image")
                source_image = config.fallback_image

    try:
        frame = composite_frame(source_image, config.logo_path, config.width, config.height)
    except Exception as exc:
        log.info(f"Primary render failed ({exc}); trying fallback image")
        try:
            frame = composite_frame(config.fallback_image, config.logo_path, config.width, config.height)
        except Exception as fallback_exc:
            print(f"Unable to render fallback image: {fallback_exc}")
            return 1

    if args.test:
        frame.save(TEST_OUTPUT)
        log.info(f"Rendered test image: {TEST_OUTPUT}")
        return 0

    try:
        write_framebuffer(frame, config.fb_device, config.width, config.height)
        log.info(f"Rendered one frame to {config.fb_device}")
        return 0
    except Exception as exc:
        log.info(f"Framebuffer write failed ({exc}); trying fallback framebuffer render")
        try:
            fallback_frame = composite_frame(config.fallback_image, config.logo_path, config.width, config.height)
            write_framebuffer(fallback_frame, config.fb_device, config.width, config.height)
            log.info(f"Rendered fallback frame to {config.fb_device}")
            return 0
        except Exception as fallback_exc:
            print(f"Unable to render to framebuffer: {fallback_exc}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())






