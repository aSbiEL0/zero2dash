#!/usr/bin/env python3
"""Refresh filtered Bee Network tram alerts for the Firswood tram module."""

from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import logging
import re
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _config import get_env, report_validation_errors

DEFAULT_ALERTS_URL = "https://tfgm.com/tram-improvement-works/"
DEFAULT_CACHE_PATH = MODULE_DIR / "tram_alerts.json"
DEFAULT_TIMEOUT_SECS = 20.0
DEFAULT_USER_AGENT = "zero2dash-trams/1.0"
ROUTE_KEYWORDS = (
    "firswood",
    "cornbrook",
    "trafford centre",
    "deansgate",
    "victoria",
    "rochdale",
    "shaw and crompton",
    "metrolink",
    "tram",
)


@dataclass
class Config:
    alerts_url: str
    cache_path: Path
    timeout_secs: float
    user_agent: str


@dataclass(frozen=True)
class AlertItem:
    title: str
    detail: str
    source_url: str

    @property
    def ticker_text(self) -> str:
        return self.title if not self.detail else f"{self.title}: {self.detail}"


class _SectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_tag = ""
        self._capture_script = False
        self._script_type = ""
        self.sections: list[dict[str, str]] = []
        self.scripts: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._current_tag = tag.lower()
        if tag.lower() == "script":
            self._capture_script = True
            self._script_type = dict((name.lower(), value or "") for name, value in attrs).get("type", "").lower()

    def handle_endtag(self, tag: str) -> None:
        self._current_tag = ""
        if tag.lower() == "script":
            self._capture_script = False
            self._script_type = ""

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._capture_script:
            self.scripts.append((self._script_type, text))
            return
        if self._current_tag in {"h1", "h2", "h3", "h4"}:
            self.sections.append({"title": text, "detail": ""})
            return
        if self._current_tag == "p":
            if self.sections:
                existing = self.sections[-1]["detail"]
                self.sections[-1]["detail"] = f"{existing} {text}".strip()
            else:
                self.sections.append({"title": text, "detail": ""})


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


def expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _as_float(name: str, value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"expected number, got {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh filtered Bee Network tram alerts cache.")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and exit.")
    parser.add_argument("--force-refresh", action="store_true", help="Rewrite cache even if content is unchanged.")
    parser.add_argument("--self-test", action="store_true", help="Run inline smoke tests and exit.")
    return parser.parse_args()


def validate_config() -> tuple[Config | None, list[str]]:
    errors: list[str] = []

    def record(name: str, *, default: Any = None, validator: Any = None) -> Any:
        try:
            return get_env(name, default=default, validator=validator)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    alerts_url = str(record("TRAM_ALERTS_URL", default=DEFAULT_ALERTS_URL)).strip()
    cache_raw = record("TRAM_ALERTS_CACHE_PATH", default=str(DEFAULT_CACHE_PATH))
    timeout_secs = float(record("TRAM_ALERTS_TIMEOUT", default=DEFAULT_TIMEOUT_SECS, validator=lambda value: _as_float("TRAM_ALERTS_TIMEOUT", value)))
    user_agent = str(record("TRAM_ALERTS_USER_AGENT", default=DEFAULT_USER_AGENT)).strip() or DEFAULT_USER_AGENT
    if not alerts_url:
        errors.append("TRAM_ALERTS_URL must not be blank")
    if errors:
        return None, errors
    return Config(alerts_url=alerts_url, cache_path=expand_path(str(cache_raw)), timeout_secs=timeout_secs, user_agent=user_agent), []


def download_alert_source(config: Config) -> tuple[str, str]:
    request = urllib.request.Request(config.alerts_url, headers={"User-Agent": config.user_agent, "Accept": "application/json,text/html;q=0.9,*/*;q=0.1"})
    with urllib.request.urlopen(request, timeout=config.timeout_secs) as response:  # nosec B310
        content_type = response.headers.get_content_type()
        payload = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    if not payload.strip():
        raise ValueError("alerts response was empty")
    return payload, content_type


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _extract_candidate_dicts(value: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if isinstance(value, dict):
        results.append(value)
        for child in value.values():
            results.extend(_extract_candidate_dicts(child))
    elif isinstance(value, list):
        for child in value:
            results.extend(_extract_candidate_dicts(child))
    return results


def dedupe_alerts(items: list[AlertItem]) -> list[AlertItem]:
    unique: list[AlertItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.title.lower(), item.detail.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def parse_structured_alerts(payload_text: str, source_url: str) -> list[AlertItem]:
    text = payload_text.strip()
    json_candidates: list[Any] = []
    if text.startswith("{") or text.startswith("["):
        try:
            json_candidates.append(json.loads(text))
        except json.JSONDecodeError:
            pass
    parser = _SectionParser()
    parser.feed(payload_text)
    for script_type, script_text in parser.scripts:
        if "json" not in script_type:
            continue
        try:
            json_candidates.append(json.loads(script_text))
        except json.JSONDecodeError:
            continue
    alerts: list[AlertItem] = []
    for candidate in json_candidates:
        for item in _extract_candidate_dicts(candidate):
            title = _normalise_text(str(item.get("title") or item.get("headline") or item.get("name") or ""))
            detail = _normalise_text(str(item.get("description") or item.get("text") or item.get("body") or ""))
            if not title and not detail:
                continue
            alerts.append(AlertItem(title=title or detail[:80], detail=detail if detail != title else "", source_url=source_url))
    return dedupe_alerts(alerts)


def parse_html_alerts(payload_text: str, source_url: str) -> list[AlertItem]:
    parser = _SectionParser()
    parser.feed(payload_text)
    alerts: list[AlertItem] = []
    for section in parser.sections:
        title = _normalise_text(section.get("title", ""))
        detail = _normalise_text(section.get("detail", ""))
        if title:
            alerts.append(AlertItem(title=title, detail=detail if detail != title else "", source_url=source_url))
    return dedupe_alerts(alerts)


def alert_matches_route(item: AlertItem) -> bool:
    haystack = f"{item.title} {item.detail}".lower()
    if "tram" in haystack or "metrolink" in haystack:
        if any(keyword in haystack for keyword in ROUTE_KEYWORDS):
            return True
        return True
    return any(keyword in haystack for keyword in ROUTE_KEYWORDS)


def filter_alerts(items: list[AlertItem]) -> list[AlertItem]:
    return [item for item in items if alert_matches_route(item)]


def build_alerts_cache(items: list[AlertItem], *, source_url: str, generated_at: datetime | None = None) -> dict[str, Any]:
    generated = generated_at or datetime.now(timezone.utc)
    return {
        "generated_at": generated.isoformat(),
        "source_url": source_url,
        "items": [
            {
                "title": item.title,
                "detail": item.detail,
                "ticker_text": item.ticker_text,
                "source_url": item.source_url,
            }
            for item in items
        ],
        "message": "No current tram alerts" if not items else "",
    }




def load_repo_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env")

def save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def run_once(*, force_refresh: bool = False, config_override: Config | None = None) -> int:
    configure_logging()

    load_repo_env()
    config = config_override
    if config is None:
        config, errors = validate_config()
        if errors:
            report_validation_errors("tram_alerts_refresh.py", errors)
            return 1
    assert config is not None

    try:
        payload_text, content_type = download_alert_source(config)
        alerts = parse_structured_alerts(payload_text, config.alerts_url)
        if not alerts and content_type != "application/json":
            alerts = parse_html_alerts(payload_text, config.alerts_url)
        payload = build_alerts_cache(filter_alerts(alerts), source_url=config.alerts_url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, ValueError) as exc:
        logging.error("Unable to refresh tram alerts cache: %s", exc)
        if config.cache_path.exists():
            logging.info("Preserving previous alerts cache: %s", config.cache_path)
            return 0
        return 1

    candidate = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if not force_refresh and config.cache_path.exists() and config.cache_path.read_text(encoding="utf-8") == candidate:
        logging.info("Tram alerts cache already current; no refresh required.")
        return 0
    save_cache(config.cache_path, payload)
    logging.info("Wrote tram alerts cache: %s", config.cache_path)
    return 0


def run_self_tests() -> int:
    structured = json.dumps({"items": [{"title": "Tram disruption at Cornbrook", "description": "Services between Firswood and Trafford Centre are delayed."}, {"title": "Bus diversion", "description": "Not relevant."}]})
    alerts = parse_structured_alerts(structured, "https://example.invalid")
    filtered = filter_alerts(alerts)
    if [item.title for item in filtered] != ["Tram disruption at Cornbrook"]:
        raise AssertionError("structured filtering should retain relevant tram alert")
    html_payload = "<html><body><h2>Metrolink service change</h2><p>Trafford Centre services are terminating early at Deansgate.</p></body></html>"
    html_alerts = filter_alerts(parse_html_alerts(html_payload, "https://example.invalid"))
    if not html_alerts:
        raise AssertionError("html fallback should extract relevant alert")
    empty_payload = build_alerts_cache([], source_url="https://example.invalid", generated_at=datetime(2026, 3, 12, 9, 30, tzinfo=timezone.utc))
    if empty_payload["message"] != "No current tram alerts":
        raise AssertionError("empty payload should advertise no current alerts")
    print("[tram_alerts_refresh.py] Self tests passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_tests()

    load_repo_env()
    config, errors = validate_config()
    if errors:
        report_validation_errors("tram_alerts_refresh.py", errors)
        return 1
    if args.check_config:
        print("[tram_alerts_refresh.py] Configuration check passed.")
        return 0
    return run_once(force_refresh=args.force_refresh, config_override=config)


if __name__ == "__main__":
    raise SystemExit(main())
