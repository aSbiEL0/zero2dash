#!/usr/bin/env python3
"""Shared Pi-hole API helpers for framebuffer dashboard scripts."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class PiHoleClient:
    host: str
    scheme: str
    verify_tls: str
    ca_bundle: str
    password: str
    api_token: str
    request_timeout: float

    def __post_init__(self) -> None:
        self._sid: str | None = None
        self._sid_expiry = 0.0
        self.auth_mode = detect_auth_mode(self.password, self.api_token)
        self.base_url = normalize_host(self.host, preferred_scheme=self.scheme)
        self.request_tls_verify = resolve_tls_verify(self.base_url, self.verify_tls, self.ca_bundle)

    def fetch(self) -> dict[str, Any]:
        if self.auth_mode == "legacy-token":
            raw = self._fetch_legacy_raw()
            normalized = normalize_legacy_summary(raw)
            normalized["raw_summary"] = raw
            return normalized

        try:
            raw = self._fetch_v6_raw()
            normalized = normalize_v6_summary(raw)
            normalized["raw_summary"] = raw
            return normalized
        except Exception as exc:
            v6_error = exc
            primary_summary = exception_summary(v6_error, "V6")
            if not self.api_token:
                return {
                    "total": 0,
                    "blocked": 0,
                    "percent": 0.0,
                    "ok": False,
                    "status": status_from_exception(v6_error, "V6"),
                    "source": "v6-session",
                    "failure": failure_from_exception(v6_error, source="v6"),
                }

            try:
                raw = self._fetch_legacy_raw()
                normalized = normalize_legacy_summary(raw)
                normalized["raw_summary"] = raw
                normalized["status"] = "LEGACY"
                return normalized
            except Exception as legacy_exc:
                fallback_summary = exception_summary(legacy_exc, "LEGACY")
                return {
                    "total": 0,
                    "blocked": 0,
                    "percent": 0.0,
                    "ok": False,
                    "status": f"{status_from_exception(v6_error, 'V6')} / {status_from_exception(legacy_exc, 'LEGACY')}",
                    "source": "v6+legacy",
                    "failure": {
                        "reason": failure_reason_from_exception(v6_error),
                        "summary": f"primary={primary_summary}; fallback={fallback_summary}",
                        "source": "v6+legacy",
                        "primary": primary_summary,
                        "fallback": fallback_summary,
                    },
                }

    def diagnose(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "base_url": self.base_url,
            "configured_auth_mode": self.auth_mode,
        }
        if self.auth_mode == "legacy-token":
            raw = self._fetch_legacy_raw()
            result["effective_source"] = "legacy-token"
            result["raw_summary"] = raw
            result["normalized"] = normalize_legacy_summary(raw)
            return result

        try:
            raw = self._fetch_v6_raw()
            result["effective_source"] = "v6-session"
            result["raw_summary"] = raw
            result["normalized"] = normalize_v6_summary(raw)
            return result
        except Exception as exc:
            result["v6_error"] = exception_summary(exc, "V6")
            if not self.api_token:
                raise
            raw = self._fetch_legacy_raw()
            result["effective_source"] = "legacy-token"
            result["fallback_from"] = "v6-session"
            result["raw_summary"] = raw
            result["normalized"] = normalize_legacy_summary(raw)
            return result

    def _http_json(self, url: str, *, method: str = "GET", body: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        effective_timeout = self.request_timeout if timeout is None else timeout
        context = None
        if url.startswith("https://"):
            if self.request_tls_verify is False:
                context = ssl._create_unverified_context()
            elif isinstance(self.request_tls_verify, str):
                context = ssl.create_default_context(cafile=self.request_tls_verify)
        with urllib.request.urlopen(request, timeout=effective_timeout, context=context) as response:
            return json.loads(response.read().decode("utf-8"))

    def _auth_get_sid(self) -> str:
        if not self.password:
            raise auth_failure("PIHOLE_PASSWORD is not configured")
        try:
            payload = self._http_json(
                f"{self.base_url}/api/auth",
                method="POST",
                body={"password": self.password},
                timeout=4,
            )
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise auth_failure("v6 session login rejected (check PIHOLE_PASSWORD)") from exc
            raise transport_failure(f"v6 auth HTTP error {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise transport_failure(f"v6 auth transport error: {exc.reason}") from exc

        session = payload.get("session", {}) if isinstance(payload, dict) else {}
        if not isinstance(session, dict) or not session.get("valid", False):
            raise auth_failure("v6 session response invalid (check PIHOLE_PASSWORD)")
        sid = session.get("sid")
        if not isinstance(sid, str) or not sid:
            raise ValueError("Pi-hole v6 auth response missing session.sid")
        validity = session.get("validity", 1800)
        self._sid = sid
        self._sid_expiry = time.time() + int(validity) - 10
        return sid

    def _ensure_sid(self) -> str:
        if self._sid and time.time() < self._sid_expiry:
            return self._sid
        return self._auth_get_sid()

    def _fetch_v6_raw(self) -> dict[str, Any]:
        sid = self._ensure_sid()
        url = f"{self.base_url}/api/stats/summary?sid=" + urllib.parse.quote(sid, safe="")
        try:
            payload = self._http_json(url, timeout=4)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise auth_failure("v6 summary request rejected") from exc
            raise transport_failure(f"v6 summary HTTP error {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise transport_failure(f"v6 summary transport error: {exc.reason}") from exc

        session = payload.get("session") if isinstance(payload, dict) else None
        if isinstance(session, dict) and session.get("valid") is False:
            sid = self._auth_get_sid()
            url = f"{self.base_url}/api/stats/summary?sid=" + urllib.parse.quote(sid, safe="")
            payload = self._http_json(url, timeout=4)
        if not isinstance(payload, dict):
            raise ValueError("Pi-hole v6 summary response must be a JSON object")
        return payload

    def _fetch_legacy_raw(self) -> dict[str, Any]:
        params = urllib.parse.urlencode({"summaryRaw": "", "auth": self.api_token})
        try:
            payload = self._http_json(f"{self.base_url}/admin/api.php?{params}", timeout=4)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise auth_failure("legacy token rejected (check PIHOLE_API_TOKEN)") from exc
            raise transport_failure(f"legacy HTTP error {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise transport_failure(f"legacy transport error: {exc.reason}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Pi-hole legacy summary response must be a JSON object")
        if str(payload.get("status", "")).lower() == "unauthorized":
            raise auth_failure("legacy token rejected (check PIHOLE_API_TOKEN)")
        return payload


def detect_auth_mode(password: str, api_token: str) -> str | None:
    if password:
        return "v6-session"
    if api_token:
        return "legacy-token"
    return None


def is_local_host(hostname: str) -> bool:
    normalized = hostname.strip("[]").lower()
    return normalized in {"localhost", "::1"} or normalized.startswith("127.")


def resolve_scheme(raw_host: str, preferred_scheme: str = "") -> str:
    if preferred_scheme:
        return preferred_scheme
    parsed = urllib.parse.urlsplit(raw_host)
    if parsed.scheme:
        return parsed.scheme
    hostname = parsed.hostname or raw_host.split("/")[0].split(":")[0]
    return "http" if is_local_host(hostname) else "https"


def resolve_tls_verify(base_url: str, verify_setting: str, ca_bundle: str) -> bool | str:
    normalized = verify_setting.strip().lower()
    if ca_bundle:
        return ca_bundle
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    parsed = urllib.parse.urlsplit(base_url)
    return parsed.scheme == "https" and not is_local_host(parsed.hostname or "")


def normalize_host(raw_host: str, preferred_scheme: str = "") -> str:
    host = raw_host.strip() or "127.0.0.1"
    if not host.startswith(("http://", "https://")):
        host = f"{resolve_scheme(host, preferred_scheme)}://{host}"
    parsed = urllib.parse.urlsplit(host)
    if parsed.path.startswith("/admin"):
        parsed = parsed._replace(path="")
    return urllib.parse.urlunsplit(parsed._replace(query="", fragment="")).rstrip("/")


def auth_failure(message: str) -> RuntimeError:
    return RuntimeError(f"AUTH_FAILURE: {message}")


def transport_failure(message: str) -> RuntimeError:
    return RuntimeError(f"TRANSPORT_FAILURE: {message}")


def status_from_exception(exc: Exception, label: str) -> str:
    message = str(exc)
    if message.startswith("AUTH_FAILURE:"):
        return f"{label} AUTH FAIL".strip()
    if message.startswith("TRANSPORT_FAILURE:"):
        return f"{label} NET FAIL".strip()
    return f"{label} ERROR".strip()


def failure_reason_from_exception(exc: Exception) -> str:
    message = str(exc)
    if message.startswith("AUTH_FAILURE:"):
        return "auth_failed"
    if message.startswith("TRANSPORT_FAILURE:"):
        lowered = message.lower()
        if "timed out" in lowered or "timeout" in lowered:
            return "network_timeout"
        return "network_error"
    return "unknown_error"


def exception_summary(exc: Exception, label: str) -> str:
    return f"{label} {status_from_exception(exc, '').strip()} ({exc})".strip()


def failure_from_exception(exc: Exception, source: str) -> dict[str, str]:
    return {
        "reason": failure_reason_from_exception(exc),
        "summary": exception_summary(exc, source.upper()),
        "source": source,
    }


def normalize_v6_summary(payload: dict[str, Any]) -> dict[str, Any]:
    queries = payload.get("queries")
    if not isinstance(queries, dict):
        raise ValueError("Pi-hole v6 summary missing 'queries' object")
    total = coerce_int(queries, "total", context="queries")
    blocked = coerce_int(queries, "blocked", context="queries")
    percent = coerce_float(queries, "percent_blocked", context="queries")
    return {
        "total": total,
        "blocked": blocked,
        "percent": percent,
        "ok": True,
        "status": "V6",
        "source": "v6-session",
    }


def normalize_legacy_summary(payload: dict[str, Any]) -> dict[str, Any]:
    total = coerce_int(payload, "dns_queries_today", context="legacy")
    blocked = coerce_int(payload, "ads_blocked_today", context="legacy")
    percent = coerce_float(payload, "ads_percentage_today", context="legacy")
    return {
        "total": total,
        "blocked": blocked,
        "percent": percent,
        "ok": True,
        "status": "LEGACY",
        "source": "legacy-token",
    }


def coerce_int(mapping: dict[str, Any], key: str, *, context: str) -> int:
    if key not in mapping:
        raise ValueError(f"Pi-hole {context} payload missing '{key}'")
    value = mapping.get(key)
    if isinstance(value, bool):
        raise ValueError(f"Pi-hole {context} payload field '{key}' must be numeric")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Pi-hole {context} payload field '{key}' must be an integer") from exc


def coerce_float(mapping: dict[str, Any], key: str, *, context: str) -> float:
    if key not in mapping:
        raise ValueError(f"Pi-hole {context} payload missing '{key}'")
    value = mapping.get(key)
    if isinstance(value, bool):
        raise ValueError(f"Pi-hole {context} payload field '{key}' must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Pi-hole {context} payload field '{key}' must be numeric") from exc
