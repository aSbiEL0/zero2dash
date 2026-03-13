#!/usr/bin/env python3
# Pi-hole TFT Dashboard -> direct framebuffer RGB565 (no X, no SDL)
# v6 auth handled elsewhere; this file only renders and calls API
# Manual Pi-hole stats display

import sys, time, json, urllib.request, urllib.parse, urllib.error, mmap, struct, argparse, ssl, errno
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

from _config import get_env, report_validation_errors
from display_layout import LAYOUT_2_1, centred_text_y

DEFAULT_ROOT = Path('~/zero2dash').expanduser()
SCRIPT_NAME = "piholestats_manual.py"
BACKGROUND_IMAGE_PATH = SCRIPT_DIR / "pihole-bkg.png"
# -------- CONFIG --------
FBDEV = "/dev/fb1"
W, H = 320, 240
REFRESH_SECS = 3

PIHOLE_HOST = "127.0.0.1"
PIHOLE_SCHEME = ""
PIHOLE_VERIFY_TLS = "auto"
PIHOLE_CA_BUNDLE = ""
PIHOLE_PASSWORD = ""
PIHOLE_API_TOKEN = ""
PIHOLE_AUTH_MODE = ""
COL_BG = (0, 0, 0)
COL_TXT = (245, 245, 245)
# ------------------------

_SID = None
_SID_EXP = 0.0
REQUEST_TIMEOUT = 4.0
REQUEST_TLS_VERIFY: bool | str = True
OUTPUT_IMAGE = ""
IO_RETRIES = 2
IO_RETRY_DELAY_SECS = 0.15
SESSION_CACHE_PATH = DEFAULT_ROOT / "cache" / "pihole_session_manual.json"
BACKGROUND_TEMPLATE: Image.Image | None = None


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"expected integer, got {value!r}") from exc


def _parse_float(value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"expected number, got {value!r}") from exc


def _parse_scheme(value: str) -> str:
    scheme = value.strip().lower()
    if scheme not in {"http", "https"}:
        raise ValueError("expected 'http' or 'https'")
    return scheme


def _parse_verify_tls(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"auto", "true", "false", "1", "0", "yes", "no"}:
        raise ValueError("expected one of auto/true/false")
    return normalized


def _host_requires_explicit_scheme(raw_host: str) -> bool:
    candidate = raw_host.strip()
    if not candidate:
        return False
    parsed = urllib.parse.urlsplit(candidate if "://" in candidate else f"//{candidate}")
    if parsed.scheme:
        return False
    hostname = (parsed.hostname or candidate.split("/")[0].split(":")[0]).strip("[]").lower()
    if not hostname:
        return False
    return hostname not in {"localhost", "::1"} and not hostname.startswith("127.")


def validate_config() -> tuple[dict[str, object] | None, list[str]]:
    errors: list[str] = []

    def record(name: str, *, default=None, required=False, validator=None):
        try:
            return get_env(name, default=default, required=required, validator=validator)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    fbdev = record("FB_DEVICE", default=FBDEV)
    host = record("PIHOLE_HOST", default="127.0.0.1")
    scheme = record("PIHOLE_SCHEME", default="", validator=_parse_scheme)
    verify_tls = record("PIHOLE_VERIFY_TLS", default="auto", validator=_parse_verify_tls)
    ca_bundle = record("PIHOLE_CA_BUNDLE", default="")
    password = record("PIHOLE_PASSWORD", default="")
    api_token = record("PIHOLE_API_TOKEN", default="")
    refresh_secs = record("REFRESH_SECS", default=REFRESH_SECS, validator=_parse_int)
    request_timeout = record("PIHOLE_TIMEOUT", default=REQUEST_TIMEOUT, validator=_parse_float)

    if isinstance(refresh_secs, int) and refresh_secs < 1:
        errors.append("REFRESH_SECS is invalid: must be greater than or equal to 1")
    if isinstance(request_timeout, float) and request_timeout <= 0:
        errors.append("PIHOLE_TIMEOUT is invalid: must be greater than 0")
    if ca_bundle and not Path(str(ca_bundle)).is_file():
        errors.append("PIHOLE_CA_BUNDLE is invalid: file does not exist")
    if _host_requires_explicit_scheme(str(host)) and not str(scheme):
        errors.append(
            "Remote PIHOLE_HOST requires an explicit scheme: set PIHOLE_SCHEME=http|https or include http:// / https:// in PIHOLE_HOST"
        )

    auth_mode = _detect_auth_mode(str(password), str(api_token))
    if auth_mode is None:
        errors.append(
            "Auth configuration is invalid: set PIHOLE_PASSWORD for v6 session auth or PIHOLE_API_TOKEN for legacy token auth"
        )

    if errors:
        return None, errors

    return {
        "fbdev": str(fbdev),
        "pihole_host": str(host),
        "pihole_scheme": str(scheme),
        "pihole_verify_tls": str(verify_tls),
        "pihole_ca_bundle": str(ca_bundle),
        "pihole_password": str(password),
        "pihole_api_token": str(api_token),
        "pihole_auth_mode": auth_mode,
        "request_timeout": float(request_timeout),
        "refresh_secs": int(refresh_secs),
    }, []


def parse_args():
    parser = argparse.ArgumentParser(description="Pi-hole framebuffer dashboard")
    parser.add_argument("--check-config", action="store_true", help="Validate env configuration and exit")
    parser.add_argument("--output-image", default="", help="Write rendered frame to a PNG file instead of framebuffer")
    return parser.parse_args()


def apply_config(config: dict[str, object], output_image: str = "") -> None:
    global FBDEV, PIHOLE_HOST, PIHOLE_SCHEME, PIHOLE_VERIFY_TLS, PIHOLE_CA_BUNDLE
    global PIHOLE_PASSWORD, PIHOLE_API_TOKEN, PIHOLE_AUTH_MODE, REFRESH_SECS, BASE_URL
    global REQUEST_TIMEOUT, REQUEST_TLS_VERIFY, OUTPUT_IMAGE
    FBDEV = str(config["fbdev"])
    PIHOLE_HOST = str(config["pihole_host"])
    PIHOLE_SCHEME = str(config["pihole_scheme"])
    PIHOLE_VERIFY_TLS = str(config["pihole_verify_tls"])
    PIHOLE_CA_BUNDLE = str(config["pihole_ca_bundle"])
    PIHOLE_PASSWORD = str(config["pihole_password"])
    PIHOLE_API_TOKEN = str(config["pihole_api_token"])
    PIHOLE_AUTH_MODE = str(config["pihole_auth_mode"])
    REQUEST_TIMEOUT = float(config["request_timeout"])
    REFRESH_SECS = int(config["refresh_secs"])
    OUTPUT_IMAGE = output_image.strip() or str(get_env("OUTPUT_IMAGE", default="")).strip()
    BASE_URL = _normalize_host(PIHOLE_HOST, preferred_scheme=PIHOLE_SCHEME)
    REQUEST_TLS_VERIFY = _resolve_tls_verify(BASE_URL, PIHOLE_VERIFY_TLS, PIHOLE_CA_BUNDLE)


def load_font(size, bold=False):
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def text_size(draw, text, font):
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    return x1 - x0, y1 - y0


def fit_font(draw, text: str, *, preferred_size: int, min_size: int, bold: bool, max_width: int):
    best_font = load_font(min_size, bold)
    for size in range(preferred_size, min_size - 1, -1):
        font = load_font(size, bold)
        width, _ = text_size(draw, text, font)
        if width <= max_width:
            return font
        best_font = font
    return best_font


def rgb888_to_rgb565(img_rgb):
    r, g, b = img_rgb.split()
    r = r.point(lambda i: i >> 3)
    g = g.point(lambda i: i >> 2)
    b = b.point(lambda i: i >> 3)
    arr = bytearray()
    rp = r.tobytes()
    gp = g.tobytes()
    bp = b.tobytes()
    for i in range(len(rp)):
        v = ((rp[i] & 0x1F) << 11) | ((gp[i] & 0x3F) << 5) | (bp[i] & 0x1F)
        arr += struct.pack("<H", v)
    return bytes(arr)


def _is_transient_io_error(exc: OSError) -> bool:
    return exc.errno in {
        errno.EAGAIN,
        errno.EINTR,
        errno.EBUSY,
        errno.ETIMEDOUT,
        errno.EIO,
    }


def _retry_io(action, description: str, retries: int = IO_RETRIES):
    attempt = 0
    while True:
        try:
            return action()
        except OSError as exc:
            if attempt >= retries or not _is_transient_io_error(exc):
                raise RuntimeError(f"{description} failed after {attempt + 1} attempt(s): {exc}") from exc
            attempt += 1
            time.sleep(IO_RETRY_DELAY_SECS)


def _write_framebuffer_payload(payload: bytes) -> None:
    fb_file = None
    fb_map = None
    try:
        try:
            fb_file = open(FBDEV, "r+b", buffering=0)
        except OSError as exc:
            raise RuntimeError(f"Unable to open framebuffer device {FBDEV}: {exc}") from exc

        try:
            fb_map = mmap.mmap(fb_file.fileno(), W * H * 2, mmap.MAP_SHARED, mmap.PROT_WRITE)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Unable to memory-map framebuffer {FBDEV}: {exc}") from exc

        try:
            fb_map.seek(0)
            fb_map.write(payload)
        except (BufferError, ValueError, OSError) as exc:
            raise RuntimeError(f"Unable to write frame to framebuffer {FBDEV}: {exc}") from exc
    finally:
        if fb_map is not None:
            fb_map.close()
        if fb_file is not None:
            fb_file.close()


def fb_write(img):
    if img.size != (W, H):
        img = img.resize((W, H), Image.BILINEAR)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if OUTPUT_IMAGE:
        output_path = Path(OUTPUT_IMAGE)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _retry_io(lambda: img.save(output_path, format="PNG"), f"Writing PNG output image {output_path}")
        return

    payload = rgb888_to_rgb565(img)
    _retry_io(lambda: _write_framebuffer_payload(payload), f"Framebuffer write to {FBDEV}")


def read_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None


def _is_local_host(hostname: str) -> bool:
    normalized = hostname.strip("[]").lower()
    return normalized in {"localhost", "::1"} or normalized.startswith("127.")


def _resolve_scheme(raw_host: str, preferred_scheme: str = "") -> str:
    if preferred_scheme:
        return preferred_scheme
    parsed = urllib.parse.urlsplit(raw_host)
    if parsed.scheme:
        return parsed.scheme
    hostname = parsed.hostname or raw_host.split("/")[0].split(":")[0]
    return "http" if _is_local_host(hostname) else "https"


def _resolve_tls_verify(base_url: str, verify_setting: str, ca_bundle: str):
    normalized = verify_setting.strip().lower()
    if ca_bundle:
        return ca_bundle
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    parsed = urllib.parse.urlsplit(base_url)
    return parsed.scheme == "https" and not _is_local_host(parsed.hostname or "")


def _http_json(url, method="GET", body=None, timeout=None):
    headers = {"Content-Type": "application/json"} if body is not None else {}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    effective_timeout = REQUEST_TIMEOUT if timeout is None else timeout
    context = None
    if url.startswith("https://"):
        if REQUEST_TLS_VERIFY is False:
            context = ssl._create_unverified_context()
        elif isinstance(REQUEST_TLS_VERIFY, str):
            context = ssl.create_default_context(cafile=REQUEST_TLS_VERIFY)
    with urllib.request.urlopen(req, timeout=effective_timeout, context=context) as r:
        return json.loads(r.read().decode("utf-8"))


def _normalize_host(raw_host: str, preferred_scheme: str = "") -> str:
    host = raw_host.strip()
    if not host:
        host = "127.0.0.1"
    if not host.startswith(("http://", "https://")):
        host = f"{_resolve_scheme(host, preferred_scheme)}://{host}"
    parsed = urllib.parse.urlsplit(host)
    if parsed.path.startswith("/admin"):
        parsed = parsed._replace(path="")
    cleaned = parsed._replace(query="", fragment="")
    return urllib.parse.urlunsplit(cleaned).rstrip("/")


BASE_URL = _normalize_host(PIHOLE_HOST, preferred_scheme=PIHOLE_SCHEME)


def _detect_auth_mode(password: str, api_token: str) -> str | None:
    if password:
        return "v6-session"
    if api_token:
        return "legacy-token"
    return None


def _auth_failure(msg: str) -> RuntimeError:
    return RuntimeError(f"AUTH_FAILURE: {msg}")


def _transport_failure(msg: str) -> RuntimeError:
    return RuntimeError(f"TRANSPORT_FAILURE: {msg}")


def _load_cached_sid() -> bool:
    global _SID, _SID_EXP
    try:
        payload = json.loads(SESSION_CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False

    sid = payload.get("sid")
    expires_at = payload.get("expires_at")
    if not isinstance(sid, str) or not sid:
        return False
    if not isinstance(expires_at, (int, float)):
        return False
    if time.time() >= float(expires_at):
        return False

    _SID = sid
    _SID_EXP = float(expires_at)
    return True


def _persist_sid() -> None:
    if not _SID or _SID_EXP <= time.time():
        return
    try:
        SESSION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSION_CACHE_PATH.write_text(
            json.dumps({"sid": _SID, "expires_at": _SID_EXP}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _auth_get_sid():
    global _SID, _SID_EXP
    if not PIHOLE_PASSWORD:
        raise _auth_failure("PIHOLE_PASSWORD is not configured")
    try:
        js = _http_json(f"{BASE_URL}/api/auth", method="POST", body={"password": PIHOLE_PASSWORD}, timeout=4)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise _auth_failure("v6 session login rejected (check PIHOLE_PASSWORD)") from exc
        raise _transport_failure(f"v6 auth HTTP error {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise _transport_failure(f"v6 auth transport error: {exc.reason}") from exc
    sess = js.get("session", {})
    if not sess.get("valid", False):
        raise _auth_failure("v6 session response invalid (check PIHOLE_PASSWORD)")
    _SID = sess["sid"]
    _SID_EXP = time.time() + int(sess.get("validity", 1800)) - 10
    _persist_sid()
    return _SID


def _ensure_sid():
    if _SID and time.time() < _SID_EXP:
        return _SID
    if _load_cached_sid():
        return _SID
    return _auth_get_sid()


def fetch_pihole():
    if PIHOLE_AUTH_MODE == "legacy-token":
        return _fetch_legacy_summary()

    try:
        sid = _ensure_sid()
        url = f"{BASE_URL}/api/stats/summary?sid=" + urllib.parse.quote(sid, safe="")
        d = _http_json(url, timeout=4)
        if d.get("session", {}).get("valid") is False:
            sid = _auth_get_sid()
            url = f"{BASE_URL}/api/stats/summary?sid=" + urllib.parse.quote(sid, safe="")
            d = _http_json(url, timeout=4)
        q = d.get("queries", {})
        total = int(q.get("total", d.get("dns_queries_today", 0)))
        blocked = int(q.get("blocked", d.get("ads_blocked_today", 0)))
        percent = float(q.get("percent_blocked", d.get("ads_percentage_today", 0.0)))
        return {
            "total": total,
            "blocked": blocked,
            "percent": percent,
            "ok": True,
            "status": "OK",
        }
    except Exception as exc:
        v6_error = exc
        primary_summary = _exception_summary(v6_error, "V6")
        if not PIHOLE_API_TOKEN:
            return {
                "total": 0,
                "blocked": 0,
                "percent": 0.0,
                "ok": False,
                "status": _status_from_exception(v6_error, "AUTH ONLY"),
                "failure": _failure_from_exception(v6_error, source="v6"),
            }

        legacy = _fetch_legacy_summary()
        if legacy["ok"]:
            legacy["status"] = "LEGACY"
            return legacy

        fallback_summary = legacy.get("failure", {}).get("summary") or legacy.get("status", "LEGACY FAIL")
        print(
            f"[{SCRIPT_NAME}] Summary fetch failed. primary={primary_summary}; fallback={fallback_summary}",
            file=sys.stderr,
        )
        return {
            "total": 0,
            "blocked": 0,
            "percent": 0.0,
            "ok": False,
            "status": f"{_status_from_exception(v6_error, 'V6')} / {legacy.get('status', 'LEGACY FAIL')}",
            "failure": {
                "reason": _failure_reason_from_exception(v6_error),
                "summary": f"primary={primary_summary}; fallback={fallback_summary}",
                "source": "v6+legacy",
                "primary": primary_summary,
                "fallback": fallback_summary,
            },
        }


def _fetch_legacy_summary():
    try:
        params = {"summaryRaw": "", "auth": PIHOLE_API_TOKEN}
        query = urllib.parse.urlencode(params)
        legacy = _http_json(f"{BASE_URL}/admin/api.php?{query}", timeout=4)
        if str(legacy.get("status", "")).lower() == "unauthorized":
            raise _auth_failure("legacy token rejected (check PIHOLE_API_TOKEN)")
        return {
            "total": int(legacy.get("dns_queries_today", 0)),
            "blocked": int(legacy.get("ads_blocked_today", 0)),
            "percent": float(legacy.get("ads_percentage_today", 0.0)),
            "ok": True,
            "status": "OK",
        }
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            failure_exc = _auth_failure("legacy token rejected (check PIHOLE_API_TOKEN)")
            message = _status_from_exception(failure_exc, "LEGACY")
        else:
            failure_exc = _transport_failure(f"legacy HTTP error {exc.code}")
            message = _status_from_exception(failure_exc, "LEGACY")
        return {
            "total": 0,
            "blocked": 0,
            "percent": 0.0,
            "ok": False,
            "status": message,
            "failure": _failure_from_exception(failure_exc, source="legacy"),
        }
    except urllib.error.URLError as exc:
        failure_exc = _transport_failure(f"legacy transport error: {exc.reason}")
        message = _status_from_exception(failure_exc, "LEGACY")
        return {
            "total": 0,
            "blocked": 0,
            "percent": 0.0,
            "ok": False,
            "status": message,
            "failure": _failure_from_exception(failure_exc, source="legacy"),
        }
    except Exception as exc:
        return {
            "total": 0,
            "blocked": 0,
            "percent": 0.0,
            "ok": False,
            "status": _status_from_exception(exc, "LEGACY"),
            "failure": _failure_from_exception(exc, source="legacy"),
        }


def _status_from_exception(exc: Exception, label: str) -> str:
    message = str(exc)
    if message.startswith("AUTH_FAILURE:"):
        return f"{label} AUTH FAIL"
    if message.startswith("TRANSPORT_FAILURE:"):
        return f"{label} NET FAIL"
    return f"{label} ERROR"


def _failure_reason_from_exception(exc: Exception) -> str:
    message = str(exc)
    if message.startswith("AUTH_FAILURE:"):
        return "auth_failed"
    if message.startswith("TRANSPORT_FAILURE:"):
        lowered = message.lower()
        if "timed out" in lowered or "timeout" in lowered:
            return "network_timeout"
        return "network_error"
    return "unknown_error"


def _exception_summary(exc: Exception, label: str) -> str:
    return f"{label} {_status_from_exception(exc, '').strip()} ({exc})"


def _failure_from_exception(exc: Exception, source: str) -> dict[str, str]:
    return {
        "reason": _failure_reason_from_exception(exc),
        "summary": _exception_summary(exc, source.upper()),
        "source": source,
    }


def _load_background_template() -> Image.Image:
    global BACKGROUND_TEMPLATE
    if BACKGROUND_TEMPLATE is None:
        try:
            BACKGROUND_TEMPLATE = Image.open(BACKGROUND_IMAGE_PATH).convert("RGB")
        except OSError:
            BACKGROUND_TEMPLATE = Image.new("RGB", (W, H), COL_BG)
    return BACKGROUND_TEMPLATE.copy()


def _format_temp(temp_c: float | None) -> str:
    if temp_c is None:
        return "N/A"
    return f"{temp_c:0.1f}\N{DEGREE SIGN}C"


def _draw_stat_row(draw, *, y: int, label: str, value: str, label_x: int, value_right: int):
    label_font = load_font(20, False)
    value_font = fit_font(draw, value, preferred_size=20, min_size=10, bold=False, max_width=LAYOUT_2_1.right.width)
    draw.text((label_x, centred_text_y(label_font, label, y)), label, font=label_font, fill=COL_TXT)
    draw.text(
        (value_right - text_size(draw, value, value_font)[0], centred_text_y(value_font, value, y)),
        value,
        font=value_font,
        fill=COL_TXT,
    )


def draw_frame(stats, temp_c):
    img = _load_background_template()
    if img.size != (W, H):
        img = img.resize((W, H), Image.BILINEAR)
    d = ImageDraw.Draw(img)

    rows = [
        ("Status:", stats["status"] if not stats["ok"] else "OK"),
        ("Total:", str(stats["total"])),
        ("Blocked:", str(stats["blocked"])),
        ("% blocked:", f"{stats['percent']:0.1f}%"),
        ("Pi Temp:", _format_temp(temp_c)),
    ]

    for index, (label, value) in enumerate(rows):
        _draw_stat_row(
            d,
            y=LAYOUT_2_1.row_centre_y(index),
            label=label,
            value=value,
            label_x=LAYOUT_2_1.left.left,
            value_right=LAYOUT_2_1.right.right,
        )

    return img


def main():
    args = parse_args()

    load_dotenv(DEFAULT_ROOT / ".env")
    config, errors = validate_config()
    if errors:
        report_validation_errors(SCRIPT_NAME, errors)
        return 1
    assert config is not None

    if args.check_config:
        print(f"[{SCRIPT_NAME}] Configuration check passed.")
        return 0

    apply_config(config, output_image=args.output_image)

    if not OUTPUT_IMAGE and not Path(FBDEV).exists():
        print(f"Framebuffer {FBDEV} not found.", file=sys.stderr)
        return 1

    cached = {"total": 0, "blocked": 0, "percent": 0.0, "ok": False, "status": "AUTH ONLY ERROR"}
    try:
        _auth_get_sid()
    except Exception:
        pass

    while True:
        s = fetch_pihole()
        if s["ok"]:
            cached = s
        else:
            cached["ok"] = False
            cached["status"] = s["status"]

        temp_c = read_temp_c()
        frame = draw_frame(cached, temp_c)
        fb_write(frame)
        if OUTPUT_IMAGE:
            print(f"[{SCRIPT_NAME}] Rendered test frame to {OUTPUT_IMAGE}.")
            return 0
        time.sleep(REFRESH_SECS)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass




