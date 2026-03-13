#!/usr/bin/env python3
"""Fetch GBP/PLN from NBP and render the currency image."""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _config import get_env, report_validation_errors

DEFAULT_OUTPUT_PATH = MODULE_DIR / "current-currency.png"
DEFAULT_BACKGROUND_PATH = MODULE_DIR / "currency-bkg.png"
DEFAULT_STATE_PATH = REPO_ROOT / "cache" / "currency_state.json"
DEFAULT_API_BASE = "https://api.nbp.pl/api"
DEFAULT_SOURCE_LABEL = "source: api.nbp.pl"
DEFAULT_TIMEOUT_SECS = 10.0
RATE_CHANGE_THRESHOLD = 0.01


@dataclass
class Config:
    output_path: Path
    background_path: Path
    state_path: Path
    api_base: str
    timeout_secs: float


@dataclass
class RateSnapshot:
    rate: float
    effective_date: date
    fetched_at: datetime
    source_label: str = DEFAULT_SOURCE_LABEL

    def display_rate(self) -> str:
        return f"{self.rate:.2f}"


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch GBP/PLN from NBP and render the currency image.")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and exit.")
    parser.add_argument("--force-refresh", action="store_true", help="Rewrite the output image even if unchanged.")
    parser.add_argument("--self-test", action="store_true", help="Run inline smoke tests and exit.")
    return parser.parse_args()


def _as_float(name: str, value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"expected number, got {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return parsed


def validate_config() -> tuple[Config | None, list[str]]:
    errors: list[str] = []

    def record(name: str, *, default: Any = None, required: bool = False, validator: Any = None) -> Any:
        try:
            return get_env(name, default=default, required=required, validator=validator)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    output_raw = record("CURRENCY_OUTPUT_PATH", default=str(DEFAULT_OUTPUT_PATH))
    background_raw = record("CURRENCY_BACKGROUND_IMAGE", default=str(DEFAULT_BACKGROUND_PATH))
    state_raw = record("CURRENCY_STATE_PATH", default=str(DEFAULT_STATE_PATH))
    api_base = str(record("CURRENCY_NBP_API_BASE", default=DEFAULT_API_BASE)).rstrip("/")
    timeout_secs = float(record("CURRENCY_API_TIMEOUT", default=DEFAULT_TIMEOUT_SECS, validator=lambda v: _as_float("CURRENCY_API_TIMEOUT", v)))

    output_path = expand_path(str(output_raw))
    background_path = expand_path(str(background_raw))
    state_path = expand_path(str(state_raw))

    if not background_path.exists():
        errors.append(f"CURRENCY_BACKGROUND_IMAGE not found: {background_path}")

    if errors:
        return None, errors

    return Config(
        output_path=output_path,
        background_path=background_path,
        state_path=state_path,
        api_base=api_base,
        timeout_secs=timeout_secs,
    ), []


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def last_success_from_state(state: dict[str, Any]) -> RateSnapshot | None:
    payload = state.get("last_success")
    if not isinstance(payload, dict):
        return None

    rate = payload.get("rate")
    effective_date = _parse_date(str(payload.get("effective_date", "")))
    fetched_at = _parse_iso_datetime(str(payload.get("fetched_at", "")))
    if not isinstance(rate, (int, float)) or effective_date is None or fetched_at is None:
        return None

    return RateSnapshot(
        rate=float(rate),
        effective_date=effective_date,
        fetched_at=fetched_at,
        source_label=str(payload.get("source_label", DEFAULT_SOURCE_LABEL)) or DEFAULT_SOURCE_LABEL,
    )


def _nbp_json(url: str, timeout_secs: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_secs) as response:  # nosec B310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("NBP API response must be a JSON object")
    return payload


def fetch_recent_snapshots(api_base: str, timeout_secs: float) -> list[RateSnapshot]:
    payload = _nbp_json(f"{api_base}/exchangerates/rates/A/GBP/last/2/?format=json", timeout_secs)
    rates = payload.get("rates")
    if not isinstance(rates, list) or not rates:
        raise ValueError("NBP API response missing rates")

    snapshots: list[RateSnapshot] = []
    fetched_at = datetime.now().astimezone()
    for entry in rates:
        if not isinstance(entry, dict):
            continue
        mid = entry.get("mid")
        effective_date = _parse_date(str(entry.get("effectiveDate", "")))
        if not isinstance(mid, (int, float)) or effective_date is None:
            continue
        snapshots.append(RateSnapshot(rate=float(mid), effective_date=effective_date, fetched_at=fetched_at))

    if not snapshots:
        raise ValueError("NBP API response missing valid mid/effectiveDate values")
    snapshots.sort(key=lambda snapshot: snapshot.effective_date)
    return snapshots


def choose_snapshot(config: Config, state: dict[str, Any], now: datetime) -> tuple[str, RateSnapshot | None, str | None]:
    try:
        snapshots = fetch_recent_snapshots(config.api_base, config.timeout_secs)
        today = now.date()
        for snapshot in reversed(snapshots):
            if snapshot.effective_date == today:
                return "ok", snapshot, None

        latest = snapshots[-1]
        logging.info("NBP has not published today's GBP rate yet; using the latest available rate from %s.", latest.effective_date.isoformat())
        return "ok", latest, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, ValueError) as exc:
        logging.warning("NBP fetch failed: %s", exc)

    cached = last_success_from_state(state)
    if cached is not None:
        logging.warning("Falling back to cached last success from %s.", cached.effective_date.isoformat())
        return "ok", cached, None

    return "error", None, "Rate update unavailable"

def load_font(size: int, *, bold: bool = False) -> Any:
    from PIL import ImageFont

    env_name = "CURRENCY_FONT_PATH_BOLD" if bold else "CURRENCY_FONT_PATH"
    env_candidates = [entry.strip() for entry in os.getenv(env_name, "").split(",") if entry.strip()]
    if bold:
        default_candidates = [
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
    else:
        default_candidates = [
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]

    for candidate in env_candidates + default_candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _fit_font(draw: Any, text: str, *, width_limit: int, initial_size: int, bold: bool = True, stroke_width: int = 0) -> Any:
    size = initial_size
    while size >= 10:
        font = load_font(size, bold=bold)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        if (bbox[2] - bbox[0]) <= width_limit:
            return font
        size -= 2
    return load_font(10, bold=bold)


def _draw_text_with_shadow(
    draw: Any,
    position: tuple[int, int],
    text: str,
    *,
    font: Any,
    fill: tuple[int, int, int, int],
    shadow_fill: tuple[int, int, int, int],
    shadow_offset: tuple[int, int],
) -> None:
    shadow_x, shadow_y = shadow_offset
    draw.text((position[0] + shadow_x, position[1] + shadow_y), text, font=font, fill=shadow_fill)
    draw.text(position, text, font=font, fill=fill)


def render_currency_image(background_path: Path, output_path: Path, display_date: str, status: str, snapshot: RateSnapshot | None, message: str | None) -> None:
    from PIL import Image, ImageDraw

    with Image.open(background_path) as raw_background:
        frame = raw_background.convert("RGBA")

    width, height = frame.size
    draw = ImageDraw.Draw(frame)
    white = (255, 255, 255, 255)
    shadow = (0, 0, 0, 144)
    shadow_offset = (max(1, width // 160), max(2, height // 120))
    centre_x = width // 2
    pair_text = "GBP / PLN"
    pair_font = load_font(max(20, width // 15), bold=True)
    date_font = load_font(max(20, width // 14), bold=True)

    if status == "ok" and snapshot is not None:
        pair_bbox = draw.textbbox((0, 0), pair_text, font=pair_font)
        pair_w = pair_bbox[2] - pair_bbox[0]
        pair_h = pair_bbox[3] - pair_bbox[1]
        rate_text = snapshot.display_rate()
        rate_font = _fit_font(draw, rate_text, width_limit=int(width * 0.54), initial_size=max(84, width // 3), bold=True)
        gap = max(3, width // 100)
        rate_size = getattr(rate_font, "size", 84)
        suffix_text = "zł"

        while True:
            suffix_font = load_font(max(22, int(rate_size * 0.58)), bold=True)
            rate_bbox = draw.textbbox((0, 0), rate_text, font=rate_font)
            suffix_bbox = draw.textbbox((0, 0), suffix_text, font=suffix_font)
            rate_w = rate_bbox[2] - rate_bbox[0]
            suffix_w = suffix_bbox[2] - suffix_bbox[0]
            total_w = rate_w + gap + suffix_w
            if total_w <= int(width * 0.66) or rate_size <= 10:
                break
            rate_size -= 2
            rate_font = load_font(rate_size, bold=True)

        date_bbox = draw.textbbox((0, 0), display_date, font=date_font)
        date_w = date_bbox[2] - date_bbox[0]
        pair_y = int(height * 0.34)
        value_y = pair_y + pair_h + int(height * 0.05)
        rate_bottom = value_y + rate_bbox[3]
        suffix_y = rate_bottom - suffix_bbox[3]
        date_y = value_y + (rate_bbox[3] - rate_bbox[1]) + int(height * 0.06)
        start_x = (width - total_w) // 2

        _draw_text_with_shadow(
            draw,
            (centre_x - (pair_w // 2), pair_y),
            pair_text,
            font=pair_font,
            fill=white,
            shadow_fill=shadow,
            shadow_offset=shadow_offset,
        )
        _draw_text_with_shadow(
            draw,
            (start_x, value_y),
            rate_text,
            font=rate_font,
            fill=white,
            shadow_fill=shadow,
            shadow_offset=shadow_offset,
        )
        _draw_text_with_shadow(
            draw,
            (start_x + rate_w + gap, suffix_y),
            suffix_text,
            font=suffix_font,
            fill=white,
            shadow_fill=shadow,
            shadow_offset=shadow_offset,
        )
        _draw_text_with_shadow(
            draw,
            (centre_x - (date_w // 2), date_y),
            display_date,
            font=date_font,
            fill=white,
            shadow_fill=shadow,
            shadow_offset=shadow_offset,
        )
    else:
        message_text = message or "Rate update unavailable"
        message_font = _fit_font(draw, message_text, width_limit=int(width * 0.82), initial_size=max(28, width // 10), bold=True)
        bbox = draw.textbbox((0, 0), message_text, font=message_font)
        msg_w = bbox[2] - bbox[0]
        msg_h = bbox[3] - bbox[1]
        _draw_text_with_shadow(
            draw,
            ((width - msg_w) // 2, (height - msg_h) // 2),
            message_text,
            font=message_font,
            fill=white,
            shadow_fill=shadow,
            shadow_offset=shadow_offset,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.convert("RGB").save(output_path, format="PNG")
    logging.info("Wrote image: %s", output_path)

def state_needs_refresh(state: dict[str, Any], output_path: Path, display_date: str, status: str, snapshot: RateSnapshot | None, message: str | None) -> bool:
    if not output_path.exists():
        return True
    if state.get("last_rendered_date") != display_date:
        return True
    if state.get("last_render_status") != status:
        return True
    if status == "ok" and snapshot is not None:
        previous_rate = state.get("last_rendered_rate")
        if not isinstance(previous_rate, (int, float)):
            return True
        if abs(float(previous_rate) - snapshot.rate) > RATE_CHANGE_THRESHOLD:
            return True
        return state.get("last_rendered_effective_date") != snapshot.effective_date.isoformat()
    return state.get("last_render_error_message") != (message or "Rate update unavailable")


def update_state(state: dict[str, Any], *, display_date: str, status: str, snapshot: RateSnapshot | None, message: str | None) -> dict[str, Any]:
    next_state = dict(state)
    next_state["last_rendered_at"] = datetime.now().astimezone().isoformat()
    next_state["last_rendered_date"] = display_date
    next_state["last_render_status"] = status
    next_state["last_render_error_message"] = message or ""

    if status == "ok" and snapshot is not None:
        next_state["last_rendered_rate"] = snapshot.rate
        next_state["last_rendered_effective_date"] = snapshot.effective_date.isoformat()
        next_state["last_success"] = {
            "rate": snapshot.rate,
            "effective_date": snapshot.effective_date.isoformat(),
            "fetched_at": snapshot.fetched_at.isoformat(),
            "source_label": snapshot.source_label,
        }

    return next_state


def run_once(*, force_refresh: bool = False) -> int:
    from dotenv import load_dotenv

    configure_logging()
    load_dotenv(REPO_ROOT / ".env")
    config, errors = validate_config()
    if errors:
        report_validation_errors("currency-rate.py", errors)
        return 1
    assert config is not None

    state = load_state(config.state_path)
    now = datetime.now().astimezone()
    status, snapshot, message = choose_snapshot(config, state, now)
    if status == "ok" and snapshot is not None:
        display_date = snapshot.effective_date.strftime("%d/%m/%y")
    else:
        display_date = now.strftime("%d/%m/%y")
    if not force_refresh and not state_needs_refresh(state, config.output_path, display_date, status, snapshot, message):
        logging.info("Currency image already current; no refresh required.")
        return 0

    render_currency_image(config.background_path, config.output_path, display_date, status, snapshot, message)
    save_state(config.state_path, update_state(state, display_date=display_date, status=status, snapshot=snapshot, message=message))
    return 0


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_self_tests() -> int:
    configure_logging()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        output = tmp_path / "current-currency.png"
        state_path = tmp_path / "currency_state.json"
        background_path = tmp_path / "currency-bkg.png"

        from PIL import Image

        Image.new("RGB", (320, 240), (40, 40, 40)).save(background_path, format="PNG")

        class Handler(BaseHTTPRequestHandler):
            scenario = "today"

            def do_GET(self) -> None:  # noqa: N802
                if self.path.endswith("/last/2/?format=json"):
                    if Handler.scenario == "today":
                        payload = {"rates": [{"mid": 5.13, "effectiveDate": "2026-03-08"}, {"mid": 5.17, "effectiveDate": "2026-03-09"}]}
                    elif Handler.scenario == "latest":
                        payload = {"rates": [{"mid": 5.11, "effectiveDate": "2026-03-08"}]}
                    else:
                        payload = {"rates": [{"mid": 5.01, "effectiveDate": "2026-03-06"}]}
                    self.send_response(200)
                else:
                    payload = {"message": "Not Found"}
                    self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            config = Config(
                output_path=output,
                background_path=background_path,
                state_path=state_path,
                api_base=f"http://127.0.0.1:{server.server_port}",
                timeout_secs=5.0,
            )
            tzinfo = datetime.now().astimezone().tzinfo
            now = datetime(2026, 3, 9, 6, 0, tzinfo=tzinfo)

            status, snapshot, message = choose_snapshot(config, {}, now)
            _assert(status == "ok" and snapshot is not None and abs(snapshot.rate - 5.17) < 0.001, "today snapshot should win")

            initial_state = update_state({}, display_date="09/03/2026", status=status, snapshot=snapshot, message=message)
            save_state(state_path, initial_state)
            output.write_text("placeholder", encoding="utf-8")
            _assert(not state_needs_refresh(initial_state, output, "09/03/2026", "ok", snapshot, None), "unchanged image should not refresh")

            Handler.scenario = "latest"
            status, snapshot, message = choose_snapshot(config, {}, now)
            _assert(status == "ok" and snapshot is not None and snapshot.effective_date.isoformat() == "2026-03-08", "recent latest fallback should be accepted")

            Handler.scenario = "stale"
            status, snapshot, message = choose_snapshot(config, {}, now)
            _assert(status == "ok" and snapshot is not None and abs(snapshot.rate - 5.01) < 0.001, "latest published rate should be accepted even when older than 24 hours")

            cached_state = {
                "last_success": {
                    "rate": 5.09,
                    "effective_date": "2026-03-08",
                    "fetched_at": "2026-03-09T05:30:00+00:00",
                    "source_label": DEFAULT_SOURCE_LABEL,
                }
            }
            status, snapshot, message = choose_snapshot(config, cached_state, now)
            _assert(status == "ok" and snapshot is not None and abs(snapshot.rate - 5.09) < 0.001, "recent cached rate should be used")

            render_currency_image(background_path, output, "09/03/2026", "ok", snapshot, None)
            _assert(output.exists(), "render should write output image")
        finally:
            server.shutdown()
            server.server_close()

    print("[currency-rate.py] Self tests passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_tests()

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    config, errors = validate_config()
    if errors:
        report_validation_errors("currency-rate.py", errors)
        return 1
    if args.check_config:
        print("[currency-rate.py] Configuration check passed.")
        return 0

    return run_once(force_refresh=args.force_refresh)


if __name__ == "__main__":
    raise SystemExit(main())



