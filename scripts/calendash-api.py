#!/usr/bin/env python3
"""Generate a 320x240 Google Calendar summary image for a Raspberry Pi TFT display.

Dependencies:
  pip install google-api-python-client google-auth-oauthlib python-dotenv pillow pytz

Cron example (06:00 every day):
  0 6 * * * cd /opt/zero2dash && /usr/bin/python3 /opt/zero2dash/scripts/calendash-api.py >> /var/log/calendash.log 2>&1

Assets:
- BACKGROUND_IMAGE should be a 320x240 base image that already contains your logo/header.
- ICON_IMAGE should be a small calendar icon with transparency.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
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

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CANVAS_WIDTH = 320
CANVAS_HEIGHT = 240
TOKEN_PATH = Path("token.json")
DEFAULT_OAUTH_PORT = 8080


@dataclass
class CalendarEvent:
    starts_at: datetime
    display_date: str
    summary: str
    all_day: bool


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required env variable: {name}")
    return value


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


def load_font(preferred_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, preferred_size)
    logging.warning("No bold TTF font found; using PIL default font.")
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


def save_credentials(creds: Credentials, token_path: Path) -> None:
    token_path.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(token_path, 0o600)
    logging.info("Saved OAuth token to %s", token_path.resolve())


def get_credentials(client_id: str, client_secret: str, token_path: Path, oauth_port: int) -> Credentials:
    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        logging.info("Refreshing existing OAuth token.")
        creds.refresh(Request())
        save_credentials(creds, token_path)
        return creds

    redirect_uri = expected_redirect_uri(oauth_port)
    logging.info("Starting first-run OAuth flow on localhost:%d.", oauth_port)
    logging.info("Expected OAuth redirect URI: %s", redirect_uri)
    flow = InstalledAppFlow.from_client_config(
        build_client_config(client_id, client_secret, oauth_port),
        SCOPES,
    )
    try:
        creds = flow.run_local_server(port=oauth_port, open_browser=False, redirect_uri_trailing_slash=True)
        logging.info("OAuth callback received successfully on localhost:%d.", oauth_port)
    except Exception as exc:
        if "redirect_uri_mismatch" in str(exc):
            logging.error(
                "OAuth redirect mismatch. Add this URI to your Google OAuth client redirect list: %s",
                redirect_uri,
            )
        logging.info("Local server auth failed (%s); falling back to console flow.", exc)
        creds = flow.run_console()
    save_credentials(creds, token_path)
    return creds


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
        except (HttpError, OSError, TimeoutError) as exc:
            last_error = exc
            wait_s = 2 ** (attempt - 1)
            logging.error("Fetch failed (attempt %d/%d): %s", attempt, retries, exc)
            if attempt < retries:
                logging.info("Retrying in %d seconds...", wait_s)
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


def _center_x(width: int, object_w: int) -> int:
    return max(0, (width - object_w) // 2)


def render_image(
    output_path: Path,
    background_path: Path,
    icon_path: Path,
    events: Iterable[CalendarEvent],
    message: str | None = None,
) -> None:
    if not background_path.exists():
        raise FileNotFoundError(f"BACKGROUND_IMAGE not found: {background_path}")

    bg = Image.open(background_path).convert("RGBA").resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(bg)

    font_date = load_font(18)
    font_title = load_font(14)
    font_empty = load_font(20)
    font_more = load_font(13)

    if message:
        tw = int(draw.textlength(message, font=font_empty))
        _, ttop, _, tbottom = draw.textbbox((0, 0), message, font=font_empty)
        th = tbottom - ttop
        x = _center_x(CANVAS_WIDTH, tw)
        y = (CANVAS_HEIGHT // 2) - (th // 2) + 34
        draw.text((x, y), message, fill=(185, 187, 191, 255), font=font_empty)
    else:
        entries = list(events)

        icon = None
        if icon_path.exists():
            icon = Image.open(icon_path).convert("RGBA").resize((25, 25), Image.Resampling.LANCZOS)
        else:
            logging.warning("ICON_IMAGE not found at %s; drawing without icon", icon_path)

        box_x = 25
        box_w = CANVAS_WIDTH - (box_x * 2)
        box_h = 38
        gap = 6
        first_box_y = 82
        max_rows = (CANVAS_HEIGHT - first_box_y) // (box_h + gap)
        if max_rows < 1:
            max_rows = 1

        visible_events = entries[:max_rows]
        hidden_count = max(0, len(entries) - len(visible_events))

        for idx, event in enumerate(visible_events):
            y = first_box_y + idx * (box_h + gap)
            fill = (7, 7, 7, 235) if not event.all_day else (24, 24, 24, 235)
            outline = (183, 186, 191, 255)
            draw.rounded_rectangle(
                [box_x, y, box_x + box_w, y + box_h],
                radius=8,
                fill=fill,
                outline=outline,
                width=3,
            )

            icon_x = box_x + 12
            icon_y = y + (box_h - 25) // 2
            if icon:
                bg.alpha_composite(icon, dest=(icon_x, icon_y))

            date_x = icon_x + 34
            date_y = y + 8
            draw.text((date_x, date_y), event.display_date, font=font_date, fill=(196, 198, 202, 255))

            summary_x = date_x + 82
            summary_y = y + 12
            max_summary_w = (box_x + box_w - 10) - summary_x
            clipped_summary = truncate_text(draw, event.summary, font_title, max_summary_w)
            draw.text((summary_x, summary_y), clipped_summary, font=font_title, fill=(196, 198, 202, 255))

        if hidden_count > 0:
            more_text = "and more."
            tw = int(draw.textlength(more_text, font=font_more))
            draw.text((_center_x(CANVAS_WIDTH, tw), CANVAS_HEIGHT - 16), more_text, font=font_more, fill=(190, 190, 190, 255))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    bg.convert("RGB").save(output_path, format="PNG")
    logging.info("Wrote image: %s", output_path)


def main() -> int:
    configure_logging()
    load_dotenv()

    try:
        client_id = required_env("GOOGLE_CLIENT_ID")
        client_secret = required_env("GOOGLE_CLIENT_SECRET")
        calendar_id = required_env("GOOGLE_CALENDAR_ID")
        tz_name = required_env("TIMEZONE")
        output_path = expand_path(required_env("OUTPUT_PATH"))
        background_path = expand_path(required_env("BACKGROUND_IMAGE"))
        icon_path = expand_path(required_env("ICON_IMAGE"))
        oauth_port = optional_env_int("OAUTH_PORT", DEFAULT_OAUTH_PORT)
    except Exception as exc:
        logging.error("Configuration error: %s", exc)
        return 1

    try:
        creds = get_credentials(client_id, client_secret, TOKEN_PATH, oauth_port)
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        events = fetch_events(service, calendar_id=calendar_id, tz_name=tz_name, retries=3)

        if not events:
            render_image(
                output_path=output_path,
                background_path=background_path,
                icon_path=icon_path,
                events=[],
                message="No upcoming events",
            )
        else:
            render_image(
                output_path=output_path,
                background_path=background_path,
                icon_path=icon_path,
                events=events,
            )
        return 0
    except Exception as exc:
        logging.error("Calendar update failed: %s", exc)
        try:
            render_image(
                output_path=output_path,
                background_path=background_path,
                icon_path=icon_path,
                events=[],
                message="Failed to update calendar",
            )
            return 2
        except Exception as render_exc:
            logging.error("Also failed rendering error image: %s", render_exc)
            return 3


if __name__ == "__main__":
    raise SystemExit(main())
