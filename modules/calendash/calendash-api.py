#!/usr/bin/env python3
"""Generate a 320x240 Google Calendar summary image for a Raspberry Pi TFT display.

Dependencies:
  pip install google-api-python-client google-auth-oauthlib python-dotenv pillow pytz

Cron example (06:00 every day):
  0 6 * * * cd /home/pihole/zero2dash && /usr/bin/python3 /home/pihole/zero2dash/modules/calendash/calendash-api.py >> /var/log/calendash.log 2>&1

Assets:
- BACKGROUND_IMAGE should be a 320x240 base image that already contains your header artwork.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import json
import argparse
import hashlib
import random
import socket
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

import pytz
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from PIL import Image, ImageDraw, ImageFont
from requests import exceptions as requests_exceptions

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _config import get_env, report_validation_errors
from display_layout import BODY_ROWS, LAYOUT_2_1, aligned_text_x, centred_text_y

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CANVAS_WIDTH = 320
CANVAS_HEIGHT = 240
MODULE_DIR = SCRIPT_DIR
DEFAULT_OUTPUT_PATH = MODULE_DIR / "calendash.png"
DEFAULT_BACKGROUND_PATH = MODULE_DIR / "calendash-bkg.png"
DEFAULT_TOKEN_PATH = Path("token.json")
DEFAULT_OAUTH_PORT = 8080
DEFAULT_AUTH_MODE = "local_server"
TOKEN_METADATA_SUFFIX = ".meta.json"
RETRYABLE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}
NON_RETRYABLE_HTTP_STATUSES = {400, 401, 403, 404}
ALLOWED_AUTH_MODES = {"local_server", "console", "device_code"}


def _fallback_legacy_calendash_path(raw_value: Any, default_path: Path) -> Path:
    resolved_path = expand_path(str(raw_value))
    if resolved_path.exists():
        return resolved_path

    # Older env files pointed calendash assets at ~/zero2dash/images/.
    # Prefer the module-local asset when that legacy path no longer exists.
    legacy_images_dir = (REPO_ROOT / "images").resolve()
    try:
        is_legacy_calendash_asset = resolved_path.parent == legacy_images_dir and resolved_path.name.startswith("calendash-")
    except Exception:
        is_legacy_calendash_asset = False

    if is_legacy_calendash_asset and default_path.exists():
        logging.info(
            "Legacy calendash asset path %s not found; falling back to %s",
            resolved_path,
            default_path,
        )
        return default_path

    return resolved_path

def _normalize_scopes(raw_scopes: Any) -> set[str]:
    if isinstance(raw_scopes, str):
        return {scope for scope in raw_scopes.replace(",", " ").split() if scope}
    if isinstance(raw_scopes, (list, tuple, set)):
        return {str(scope) for scope in raw_scopes if scope}
    return set()

    def _add_scope_values(raw_value: Any) -> None:
        if raw_value is None:
            return
        if isinstance(raw_value, str):
            scope_tokens = raw_value.replace(",", " ").split()
            parsed_scopes.update(token.strip() for token in scope_tokens if token.strip())
            return
        if isinstance(raw_value, dict):
            _add_scope_values(raw_value.get("scope") or raw_value.get("scopes"))
            return
        if isinstance(raw_value, (list, tuple, set)):
            for item in raw_value:
                _add_scope_values(item)
            return

        parsed_scopes.add(str(raw_value).strip())

    _add_scope_values(raw_scopes)
    parsed_scopes.discard("")
    return parsed_scopes


def _missing_required_scopes(scopes: set[str]) -> set[str]:
    return set(SCOPES) - scopes


def _credentials_have_required_scopes(creds: Credentials) -> bool:
    token_scopes = _normalize_scopes(getattr(creds, "scopes", None))
    return not _missing_required_scopes(token_scopes)


def _interactive_auth_available(mode: str) -> bool:
    # Headless service runs must not try to start a fresh approval flow.
    if os.getenv("INVOCATION_ID"):
        return False
    if mode == "local_server":
        return sys.stdin.isatty() and sys.stdout.isatty()
    if mode == "console":
        return sys.stdin.isatty()
    return True

def _invalidate_token_file(token_path: Path, reason: str) -> None:
    logging.warning("Marking token invalid at %s: %s", token_path.resolve(), reason)
    if token_path.exists():
        token_path.unlink()


@dataclass
class CalendarEvent:
    starts_at: datetime
    display_date: str
    summary: str
    all_day: bool


@dataclass
class AuthAttemptDiagnostics:
    status: str
    mode: str
    oauth_port: int
    redirect_uri: str
    error_type: str | None = None
    error_message: str | None = None
    next_steps: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "timestamp": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "status": self.status,
            "mode": self.mode,
            "oauth_port": self.oauth_port,
            "redirect_uri": self.redirect_uri,
        }
        if self.error_type:
            payload["error_type"] = self.error_type
        if self.error_message:
            payload["error_message"] = self.error_message
        if self.next_steps:
            payload["next_steps"] = self.next_steps
        return payload


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def optional_env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {name}: {raw}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a calendar summary image.")
    parser.add_argument("--check-config", action="store_true", help="Validate env configuration and exit")
    parser.add_argument("--auth-only", action="store_true", help="Run OAuth/token setup only and exit")
    parser.add_argument(
        "--auth-mode",
        choices=sorted(ALLOWED_AUTH_MODES),
        help="OAuth flow mode: local_server, console, or device_code.",
    )
    parser.add_argument(
        "--force-token-path-reuse",
        action="store_true",
        help="Allow GOOGLE_TOKEN_PATH to match GOOGLE_TOKEN_PATH_PHOTOS and bypass token metadata mismatch checks.",
    )
    return parser.parse_args()


def _scope_fingerprint(scopes: Iterable[str]) -> str:
    canonical = "\n".join(sorted(set(scopes)))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _token_metadata_path(token_path: Path) -> Path:
    return token_path.with_name(f"{token_path.name}{TOKEN_METADATA_SUFFIX}")


def _write_token_metadata(token_path: Path, provider: str, scopes: Iterable[str]) -> None:
    metadata_path = _token_metadata_path(token_path)
    payload = {
        "provider": provider,
        "scopes": sorted(set(scopes)),
        "scope_fingerprint": _scope_fingerprint(scopes),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(metadata_path, 0o600)


def _preflight_token_path_guard(calendar_token_path: Path, force_token_path_reuse: bool) -> None:
    photos_token_path = Path(os.getenv("GOOGLE_TOKEN_PATH_PHOTOS", "~/zero2dash/token_photos.json")).expanduser().resolve()
    if calendar_token_path.resolve() != photos_token_path:
        return
    if force_token_path_reuse:
        logging.warning(
            "GOOGLE_TOKEN_PATH matches GOOGLE_TOKEN_PATH_PHOTOS (%s), but proceeding due to --force-token-path-reuse.",
            calendar_token_path.resolve(),
        )
        return
    raise ValueError(
        "Refusing to reuse a single token path for calendar and photos scripts. "
        "Update GOOGLE_TOKEN_PATH or GOOGLE_TOKEN_PATH_PHOTOS to different files, "
        "or pass --force-token-path-reuse to override intentionally."
    )


def _verify_token_metadata(token_path: Path, force_token_path_reuse: bool) -> None:
    metadata_path = _token_metadata_path(token_path)
    if not metadata_path.exists():
        return

    try:
        metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.warning("Ignoring unreadable token metadata at %s (%s).", metadata_path.resolve(), exc)
        return

    expected_provider = "google_calendar"
    expected_fingerprint = _scope_fingerprint(SCOPES)
    provider = str(metadata_payload.get("provider", "")).strip()
    scope_fingerprint = str(metadata_payload.get("scope_fingerprint", "")).strip()

    if provider == expected_provider and scope_fingerprint == expected_fingerprint:
        return

    mismatch_message = (
        f"Token metadata mismatch for {token_path.resolve()} (found provider={provider or 'unknown'}, "
        f"scope_fingerprint={scope_fingerprint or 'unknown'}; expected provider={expected_provider})."
    )
    remediation = (
        "Remediation: set GOOGLE_TOKEN_PATH to a dedicated calendar token file and "
        "set GOOGLE_TOKEN_PATH_PHOTOS to a separate photos token file. "
        "If shared token usage is intentional, rerun with --force-token-path-reuse."
    )

    if force_token_path_reuse:
        logging.warning("%s %s", mismatch_message, remediation)
        return

    raise ValueError(f"{mismatch_message} {remediation}")


def validate_timezone(value: str) -> str:
    pytz.timezone(value)
    return value


def _env_is_set(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.strip() != ""


def _record_missing_for_section(missing_by_section: dict[str, list[str]], section: str, *env_names: str) -> None:
    bucket = missing_by_section.setdefault(section, [])
    for env_name in env_names:
        if env_name not in bucket:
            bucket.append(env_name)


def report_missing_required_fields(missing_by_section: dict[str, list[str]]) -> None:
    if not missing_by_section:
        return
    print("[calendash-api.py] Missing required environment variables by section:")
    for section, env_names in missing_by_section.items():
        if not env_names:
            continue
        print(f"  - {section}:")
        for env_name in env_names:
            print(f"    - {env_name}")


def validate_config(*, require_sections: set[str]) -> tuple[dict[str, dict[str, Any]], list[str], dict[str, list[str]]]:
    errors: list[str] = []
    missing_by_section: dict[str, list[str]] = OrderedDict()

    def record(name: str, *, default: Any = None, required: bool = False, validator: Any = None) -> Any:
        try:
            return get_env(name, default=default, required=required, validator=validator)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    calendar_client_id = record("GOOGLE_CALENDAR_CLIENT_ID")
    fallback_client_id = record("GOOGLE_CLIENT_ID")
    client_id = calendar_client_id or fallback_client_id
    if "auth" in require_sections and not client_id:
        errors.append("One of GOOGLE_CALENDAR_CLIENT_ID or GOOGLE_CLIENT_ID is required but not set.")
        if not _env_is_set("GOOGLE_CALENDAR_CLIENT_ID"):
            _record_missing_for_section(missing_by_section, "auth", "GOOGLE_CALENDAR_CLIENT_ID")
        if not _env_is_set("GOOGLE_CLIENT_ID"):
            _record_missing_for_section(missing_by_section, "auth", "GOOGLE_CLIENT_ID")

    calendar_client_secret = record("GOOGLE_CALENDAR_CLIENT_SECRET")
    fallback_client_secret = record("GOOGLE_CLIENT_SECRET")
    client_secret = calendar_client_secret or fallback_client_secret
    if "auth" in require_sections and not client_secret:
        errors.append("One of GOOGLE_CALENDAR_CLIENT_SECRET or GOOGLE_CLIENT_SECRET is required but not set.")
        if not _env_is_set("GOOGLE_CALENDAR_CLIENT_SECRET"):
            _record_missing_for_section(missing_by_section, "auth", "GOOGLE_CALENDAR_CLIENT_SECRET")
        if not _env_is_set("GOOGLE_CLIENT_SECRET"):
            _record_missing_for_section(missing_by_section, "auth", "GOOGLE_CLIENT_SECRET")

    api_required = "api" in require_sections
    calendar_id = record("GOOGLE_CALENDAR_ID", required=api_required)
    tz_name = record("TIMEZONE", required=api_required, validator=validate_timezone)
    if api_required:
        if not _env_is_set("GOOGLE_CALENDAR_ID"):
            _record_missing_for_section(missing_by_section, "api", "GOOGLE_CALENDAR_ID")
        if not _env_is_set("TIMEZONE"):
            _record_missing_for_section(missing_by_section, "api", "TIMEZONE")

    rendering_required = "rendering" in require_sections
    output_raw = record("OUTPUT_PATH", default=str(DEFAULT_OUTPUT_PATH))
    background_raw = record("BACKGROUND_IMAGE", default=str(DEFAULT_BACKGROUND_PATH))

    oauth_port = record("OAUTH_PORT", default=DEFAULT_OAUTH_PORT, validator=lambda v: optional_env_int("OAUTH_PORT", DEFAULT_OAUTH_PORT))
    token_raw = record("GOOGLE_TOKEN_PATH", default=str(DEFAULT_TOKEN_PATH))
    auth_mode_raw = record("GOOGLE_AUTH_MODE", default=DEFAULT_AUTH_MODE)
    diagnostics_raw = record("GOOGLE_AUTH_DIAGNOSTICS_PATH", default="~/zero2dash/logs/calendash-auth-diagnostics.json")

    auth_mode = str(auth_mode_raw).strip().lower()
    if auth_mode not in ALLOWED_AUTH_MODES:
        errors.append(
            f"GOOGLE_AUTH_MODE must be one of {', '.join(sorted(ALLOWED_AUTH_MODES))}. Received: {auth_mode_raw!r}"
        )
        auth_mode = DEFAULT_AUTH_MODE

    output_path = _fallback_legacy_calendash_path(output_raw, DEFAULT_OUTPUT_PATH)
    background_path = _fallback_legacy_calendash_path(background_raw, DEFAULT_BACKGROUND_PATH)
    token_path = expand_path(str(token_raw))
    diagnostics_path = expand_path(str(diagnostics_raw))

    if rendering_required and not background_path.exists():
        errors.append(f"BACKGROUND_IMAGE not found: {background_path}")
    return {
        "auth": {
            "client_id": client_id,
            "client_secret": client_secret,
        },
        "api": {
            "calendar_id": calendar_id,
            "tz_name": tz_name,
        },
        "rendering": {
            "output_path": output_path,
            "background_path": background_path,
        },
        "runtime": {
            "oauth_port": int(oauth_port),
            "token_path": token_path,
            "auth_mode": auth_mode,
            "diagnostics_path": diagnostics_path,
        },
    }, errors, missing_by_section


def _next_steps_for_auth_error(mode: str, exc: Exception, redirect_uri: str, oauth_port: int) -> list[str]:
    error_text = str(exc).lower()
    steps: list[str] = []

    if "address already in use" in error_text or "cannot listen" in error_text:
        steps.append(f"Port {oauth_port} is busy. Set OAUTH_PORT to a free port (for example 8090) and retry.")
    if "redirect_uri_mismatch" in error_text:
        steps.append(f"Add this exact redirect URI in Google Cloud OAuth client settings: {redirect_uri}")
        steps.append("If you cannot change redirect URIs, retry with --auth-mode console.")
    if any(tag in error_text for tag in ["access blocked", "app is blocked", "app restricted"]):
        steps.append("On OAuth consent screen, add your Google account as a Test User or publish the app.")
    if "invalid_client" in error_text:
        steps.append("Verify GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET belong to the same OAuth client.")
        steps.append("Use a Desktop app OAuth client for local_server/console flows.")
    if mode == "device_code" and "unsupported" in error_text:
        steps.append("This google-auth-oauthlib version lacks device code flow support. Upgrade package or use --auth-mode console.")

    if not steps:
        steps.append("Review client ID/secret, OAuth consent configuration, and retry with --auth-mode console for headless environments.")
    return steps


def persist_auth_diagnostics(path: Path, details: AuthAttemptDiagnostics) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = details.as_dict()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _run_auth_flow(flow: InstalledAppFlow, mode: str, oauth_port: int) -> Credentials:
    if mode == "local_server":
        return flow.run_local_server(port=oauth_port, open_browser=False, redirect_uri_trailing_slash=True)
    if mode == "console":
        return flow.run_console()
    if mode == "device_code":
        run_device_code = getattr(flow, "run_device_authorization", None)
        if callable(run_device_code):
            return run_device_code()
        raise NotImplementedError("device_code mode is not supported by this google-auth-oauthlib version")
    raise ValueError(f"Unsupported auth mode: {mode}")


def load_font(preferred_size: int, *, use_bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    env_candidates = [p.strip() for p in os.getenv("CALENDASH_FONT_PATH", "").split(",") if p.strip()]
    if use_bold:
        default_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        default_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]

    candidates = env_candidates + default_candidates
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, preferred_size)
    logging.warning("No usable TTF font found; using PIL default font.")
    return ImageFont.load_default()


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



def manual_auth_command(auth_mode: str) -> str:
    script_path = (MODULE_DIR / "calendash-api.py").resolve()
    return f"cd {REPO_ROOT} && python3 {script_path} --auth-only --auth-mode {auth_mode}"

def save_credentials(creds: Credentials, token_path: Path) -> None:
    token_path.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(token_path, 0o600)
    _write_token_metadata(token_path, provider="google_calendar", scopes=SCOPES)
    logging.info("Saved OAuth token to %s", token_path.resolve())


def get_credentials(
    client_id: str,
    client_secret: str,
    token_path: Path,
    oauth_port: int,
    auth_mode: str,
    diagnostics_path: Path,
    force_token_path_reuse: bool,
) -> Credentials:
    creds: Credentials | None = None

    _preflight_token_path_guard(token_path, force_token_path_reuse)
    _verify_token_metadata(token_path, force_token_path_reuse)

    if token_path.exists():
        try:
            payload = json.loads(token_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logging.warning("Ignoring invalid token file at %s (%s).", token_path.resolve(), exc)
            payload = None

        if payload is not None:
            token_scopes = _normalize_scopes(payload.get("scopes") or payload.get("scope"))
            missing_scopes = _missing_required_scopes(token_scopes)
            if missing_scopes:
                expected_list = ", ".join(sorted(SCOPES))
                missing_list = ", ".join(sorted(missing_scopes))
                _invalidate_token_file(
                    token_path,
                    f"missing required calendar scopes ({missing_list}); expected at least: {expected_list}",
                )
                payload = None

        if payload is not None:
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            except Exception as exc:
                logging.warning("Unable to load token from %s (%s); re-authenticating.", token_path.resolve(), exc)

    if creds and creds.valid:
        if not _credentials_have_required_scopes(creds):
            _invalidate_token_file(token_path, "loaded token credentials are incompatible with required calendar scopes")
            creds = None
        else:
            persist_auth_diagnostics(
                diagnostics_path,
                AuthAttemptDiagnostics(status="success", mode="token_cache", oauth_port=oauth_port, redirect_uri=expected_redirect_uri(oauth_port)),
            )
            return creds

    if creds and creds.expired and creds.refresh_token:
        logging.info("Refreshing existing OAuth token.")
        try:
            creds.refresh(Request())
        except Exception as exc:
            _invalidate_token_file(token_path, f"refresh failed ({type(exc).__name__}: {exc})")
            logging.warning(
                "Token refresh failed and token was invalidated. Forcing re-authentication to restore calendar access."
            )
            creds = None

        if creds and not _credentials_have_required_scopes(creds):
            _invalidate_token_file(token_path, "refreshed token is missing required calendar scopes")
            logging.warning(
                "Refreshed OAuth token lacks required calendar scopes. Forcing re-authentication."
            )
            creds = None

        if creds:
            save_credentials(creds, token_path)
            persist_auth_diagnostics(
                diagnostics_path,
                AuthAttemptDiagnostics(status="success", mode="token_refresh", oauth_port=oauth_port, redirect_uri=expected_redirect_uri(oauth_port)),
            )
            return creds

    redirect_uri = expected_redirect_uri(oauth_port)
    logging.info("Starting OAuth flow (%s) on localhost:%d.", auth_mode, oauth_port)
    logging.info("Expected OAuth redirect URI: %s", redirect_uri)
    auth_command = manual_auth_command(auth_mode)
    if not _interactive_auth_available(auth_mode):
        next_steps = loopback_oauth_guidance(oauth_port)
        next_steps.append(f"Manual token refresh command: {auth_command}")
        persist_auth_diagnostics(
            diagnostics_path,
            AuthAttemptDiagnostics(
                status="error",
                mode=auth_mode,
                oauth_port=oauth_port,
                redirect_uri=redirect_uri,
                error_type="RuntimeError",
                error_message="interactive OAuth is disabled in this headless session",
                next_steps=next_steps,
            ),
        )
        for message in next_steps:
            logging.error(message)
        raise RuntimeError(
            "Stored calendar credentials are unavailable and interactive OAuth is disabled in this headless session. "
            f"Refresh the token manually with: {auth_command}"
        )
    flow = InstalledAppFlow.from_client_config(
        build_client_config(client_id, client_secret, oauth_port),
        SCOPES,
    )
    try:
        creds = _run_auth_flow(flow, auth_mode, oauth_port)
        if not _credentials_have_required_scopes(creds):
            raise RuntimeError(
                "Authenticated token does not include required calendar scopes. Ensure consent grants calendar.readonly access."
            )
        save_credentials(creds, token_path)
        return creds
    except Exception as exc:
        exc_text = str(exc).lower()
        next_steps = _next_steps_for_auth_error(auth_mode, exc, redirect_uri, oauth_port)
        next_steps.extend(loopback_oauth_guidance(oauth_port))
        next_steps.append(f"Manual token refresh command: {auth_command}")
        persist_auth_diagnostics(
            diagnostics_path,
            AuthAttemptDiagnostics(
                status="error",
                mode=auth_mode,
                oauth_port=oauth_port,
                redirect_uri=redirect_uri,
                error_type=type(exc).__name__,
                error_message=str(exc),
                next_steps=next_steps,
            ),
        )
        if any(tag in exc_text for tag in ["access blocked", "app is blocked", "app restricted", "invalid_client"]):
            logging.error(
                "Google blocked this OAuth client. For calendar, use a Desktop OAuth client and add your account as a test user on the consent screen."
            )
            logging.error("You can also set GOOGLE_CALENDAR_CLIENT_ID / GOOGLE_CALENDAR_CLIENT_SECRET to use a dedicated calendar OAuth client.")
        for message in next_steps:
            logging.error(message)
        raise RuntimeError("Loopback OAuth setup failed.") from exc


def parse_event_start(raw_event: dict[str, Any], tz_obj: pytz.BaseTzInfo) -> tuple[datetime, bool]:
    start = raw_event.get("start", {})
    date_time_val = start.get("dateTime")
    date_val = start.get("date")

    if date_time_val:
        parsed = datetime.fromisoformat(date_time_val.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = tz_obj.localize(parsed)
        return parsed.astimezone(tz_obj), False

    if date_val:
        parsed_date = date.fromisoformat(date_val)
        localized_midnight = tz_obj.localize(datetime.combine(parsed_date, dt_time.min))
        return localized_midnight, True

    raise ValueError("Event missing both start.dateTime and start.date")


def fetch_events(
    service: Any,
    calendar_id: str,
    tz_name: str,
    retries: int = 3,
) -> list[CalendarEvent]:
    tz_obj = pytz.timezone(tz_name)
    now_local = datetime.now(tz_obj)
    start_local = tz_obj.localize(datetime.combine(now_local.date(), dt_time.min))
    end_local = tz_obj.localize(datetime.combine(now_local.date() + timedelta(days=3), dt_time(23, 59, 59)))

    params = {
        "calendarId": calendar_id,
        "timeMin": start_local.astimezone(pytz.UTC).isoformat(),
        "timeMax": end_local.astimezone(pytz.UTC).isoformat(),
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": 250,
    }

    last_error: Exception | None = None

    def _http_status(exc: HttpError) -> int | None:
        return getattr(getattr(exc, "resp", None), "status", None)

    def _is_non_retryable(exc: Exception) -> bool:
        if isinstance(exc, HttpError):
            return _http_status(exc) in NON_RETRYABLE_HTTP_STATUSES
        return False

    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, HttpError):
            return _http_status(exc) in RETRYABLE_HTTP_STATUSES
        return isinstance(
            exc,
            (
                OSError,
                TimeoutError,
                socket.timeout,
                socket.gaierror,
                json.JSONDecodeError,
                requests_exceptions.ConnectionError,
                requests_exceptions.Timeout,
                requests_exceptions.RequestException,
            ),
        )

    def _backoff_seconds(attempt: int, *, base_delay: float = 1.0, cap_seconds: float = 16.0, jitter_max: float = 0.75) -> float:
        exponential = min(cap_seconds, base_delay * (2 ** (attempt - 1)))
        return exponential + random.uniform(0, jitter_max)

    for attempt in range(1, retries + 1):
        try:
            logging.info(
                "Fetching events from %s to %s (%s), attempt %d/%d",
                start_local.isoformat(),
                end_local.isoformat(),
                tz_name,
                attempt,
                retries,
            )
            response = service.events().list(**params).execute()
            raw_events = response.get("items", [])
            parsed: list[CalendarEvent] = []
            for raw in raw_events:
                starts_at, all_day = parse_event_start(raw, tz_obj)
                parsed.append(
                    CalendarEvent(
                        starts_at=starts_at,
                        display_date=starts_at.strftime("%d/%m"),
                        summary=(raw.get("summary") or "(No title)").strip(),
                        all_day=all_day,
                    )
                )
            parsed.sort(key=lambda event: event.starts_at)
            return parsed
        except Exception as exc:
            last_error = exc
            if _is_non_retryable(exc):
                logging.error("Fetch failed with non-retryable error (attempt %d/%d): %s", attempt, retries, exc)
                break

            if not _is_retryable(exc):
                raise

            wait_s = _backoff_seconds(attempt)
            logging.error("Fetch failed with retryable error (attempt %d/%d): %s", attempt, retries, exc)
            if attempt < retries:
                logging.info("Retrying in %.2f seconds...", wait_s)
                time.sleep(wait_s)

    assert last_error is not None
    raise RuntimeError("Failed to fetch calendar events after retries") from last_error


def truncate_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text

    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = text[:mid].rstrip() + ellipsis
        if draw.textlength(candidate, font=font) <= max_width:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + ellipsis



def render_image(
    output_path: Path,
    background_path: Path,
    events: Iterable[CalendarEvent],
    message: str | None = None,
) -> None:
    if not background_path.exists():
        raise FileNotFoundError(f"BACKGROUND_IMAGE not found: {background_path}")

    bg = Image.open(background_path).convert("RGBA").resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(bg)

    font_event = load_font(20)
    font_date = load_font(20)
    font_message = load_font(20)
    font_more = load_font(13)
    text_fill = (245, 245, 245, 255)
    muted_fill = (190, 190, 190, 255)

    if message:
        tw = int(draw.textlength(message, font=font_message))
        x = max(LAYOUT_2_1.body.left, LAYOUT_2_1.body.centre_x - (tw // 2))
        y = centred_text_y(font_message, message, LAYOUT_2_1.row_centre_y(2))
        draw.text((x, y), message, fill=muted_fill, font=font_message)
    else:
        entries = list(events)
        max_rows = max(1, BODY_ROWS - 1)
        visible_events = entries[:max_rows]
        hidden_count = max(0, len(entries) - len(visible_events))

        for idx, event in enumerate(visible_events):
            row_centre = LAYOUT_2_1.row_centre_y(idx)
            max_summary_w = max(24, LAYOUT_2_1.left.width)
            clipped_summary = truncate_text(draw, event.summary, font_event, max_summary_w)
            draw.text((LAYOUT_2_1.left.left, centred_text_y(font_event, clipped_summary, row_centre)), clipped_summary, font=font_event, fill=text_fill)
            draw.text(
                (aligned_text_x(LAYOUT_2_1.right, font_date, event.display_date, "right"), centred_text_y(font_date, event.display_date, row_centre)),
                event.display_date,
                font=font_date,
                fill=text_fill,
            )

        if hidden_count > 0:
            more_text = f"+{hidden_count} more"
            draw.text(
                (LAYOUT_2_1.left.left, centred_text_y(font_more, more_text, LAYOUT_2_1.row_centre_y(BODY_ROWS - 1))),
                more_text,
                font=font_more,
                fill=muted_fill,
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    bg.convert("RGB").save(output_path, format="PNG")
    logging.info("Wrote image: %s", output_path)


def main() -> int:
    configure_logging()
    load_dotenv()
    args = parse_args()

    required_sections = {"auth", "api", "rendering", "runtime"}
    if args.check_config or args.auth_only:
        required_sections = {"auth", "runtime"}

    config, errors, missing_by_section = validate_config(require_sections=required_sections)
    if missing_by_section:
        report_missing_required_fields(missing_by_section)
    if errors:
        report_validation_errors("calendash-api.py", errors)
        return 1

    auth_config = config["auth"]
    api_config = config["api"]
    rendering_config = config["rendering"]
    runtime_config = config["runtime"]
    selected_auth_mode = (args.auth_mode or runtime_config["auth_mode"]).strip().lower()
    if selected_auth_mode not in ALLOWED_AUTH_MODES:
        logging.error("Unsupported auth mode: %s", selected_auth_mode)
        return 1

    try:
        _preflight_token_path_guard(runtime_config["token_path"], args.force_token_path_reuse)
        _verify_token_metadata(runtime_config["token_path"], args.force_token_path_reuse)
    except ValueError as exc:
        logging.error(str(exc))
        return 1

    if args.check_config:
        print("[calendash-api.py] Configuration check passed.")
        return 0

    try:
        creds = get_credentials(
            auth_config["client_id"],
            auth_config["client_secret"],
            runtime_config["token_path"],
            runtime_config["oauth_port"],
            selected_auth_mode,
            runtime_config["diagnostics_path"],
            args.force_token_path_reuse,
        )

        if args.auth_only:
            print("[calendash-api.py] Authentication check passed.")
            return 0

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        events = fetch_events(service, calendar_id=api_config["calendar_id"], tz_name=api_config["tz_name"], retries=3)

        if not events:
            render_image(
                output_path=rendering_config["output_path"],
                background_path=rendering_config["background_path"],
                events=[],
                message="No upcoming events",
            )
        else:
            render_image(
                output_path=rendering_config["output_path"],
                background_path=rendering_config["background_path"],
                events=events,
            )
        return 0
    except Exception as exc:
        logging.error("Calendar update failed: %s", exc)
        if args.auth_only:
            logging.info("Auth-only mode; skipping fallback rendering.")
            return 1
        try:
            render_image(
                output_path=rendering_config["output_path"],
                background_path=rendering_config["background_path"],
                events=[],
                message="Failed to update calendar",
            )
            return 2
        except Exception as render_exc:
            logging.error("Failed to render fallback image: %s", render_exc)
            return 3


if __name__ == "__main__":
    raise SystemExit(main())

