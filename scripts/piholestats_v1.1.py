#!/usr/bin/env python3
# Pi-hole TFT Dashboard -> direct framebuffer RGB565 (no X, no SDL)
# Version 1.1.1 - legacy daytime variant with shared API diagnostics

from __future__ import annotations

import argparse
import errno
import json
import mmap
import struct
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

from _config import get_env, report_validation_errors
from pihole_api import PiHoleClient, detect_auth_mode

DEFAULT_ROOT = Path('~/zero2dash').expanduser()
SCRIPT_NAME = 'piholestats_v1.1.py'

FBDEV = '/dev/fb1'
W, H = 320, 240
REFRESH_SECS = 3
ACTIVE_HOURS = (7, 22)

PIHOLE_HOST = '127.0.0.1'
PIHOLE_SCHEME = ''
PIHOLE_VERIFY_TLS = 'auto'
PIHOLE_CA_BUNDLE = ''
PIHOLE_PASSWORD = ''
PIHOLE_API_TOKEN = ''
PIHOLE_AUTH_MODE = ''
TITLE = 'Pi-hole'
COL_BG = (0, 0, 0)
COL_TXT = (200, 200, 200)
COL_OK = (0, 45, 100)
COL_BAD = (100, 10, 10)
COL_MIX = (150, 100, 0)
COL_TEMP = (0, 85, 50)
COL_UP = (60, 30, 100)

REQUEST_TIMEOUT = 4.0
OUTPUT_IMAGE = ''
IO_RETRIES = 2
IO_RETRY_DELAY_SECS = 0.15
PIHOLE_CLIENT: PiHoleClient | None = None


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


def _parse_active_hours(value: str) -> tuple[int, int]:
    parts = [part.strip() for part in value.split(',')]
    if len(parts) != 2:
        raise ValueError('expected format start,end (e.g. 22,7)')
    try:
        start_hour, end_hour = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(f"expected integers in start,end, got {value!r}") from exc
    for hour in (start_hour, end_hour):
        validate_hour_bounds(hour)
    return start_hour, end_hour


def _parse_scheme(value: str) -> str:
    scheme = value.strip().lower()
    if scheme not in {'http', 'https'}:
        raise ValueError("expected 'http' or 'https'")
    return scheme


def _parse_verify_tls(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {'auto', 'true', 'false', '1', '0', 'yes', 'no'}:
        raise ValueError('expected one of auto/true/false')
    return normalized


def _host_requires_explicit_scheme(raw_host: str) -> bool:
    candidate = raw_host.strip()
    if not candidate:
        return False
    parsed = urllib.parse.urlsplit(candidate if '://' in candidate else f'//{candidate}')
    if parsed.scheme:
        return False
    hostname = (parsed.hostname or candidate.split('/')[0].split(':')[0]).strip('[]').lower()
    if not hostname:
        return False
    return hostname not in {'localhost', '::1'} and not hostname.startswith('127.')


def validate_hour_bounds(hour: int) -> None:
    if hour < 0 or hour > 23:
        raise ValueError(f'hour must be in range 0-23, got {hour}')


def is_hour_active(now_hour: int, start: int, end: int) -> bool:
    validate_hour_bounds(now_hour)
    validate_hour_bounds(start)
    validate_hour_bounds(end)
    if start <= end:
        return start <= now_hour <= end
    return now_hour >= start or now_hour <= end


def run_self_checks() -> None:
    assert is_hour_active(8, 8, 17)
    assert is_hour_active(17, 8, 17)
    assert not is_hour_active(7, 8, 17)
    assert is_hour_active(23, 22, 7)
    assert is_hour_active(3, 22, 7)
    assert not is_hour_active(12, 22, 7)
    assert is_hour_active(0, 0, 0)
    assert not is_hour_active(1, 0, 0)
    assert is_hour_active(23, 23, 2)
    assert is_hour_active(1, 23, 2)
    assert not is_hour_active(10, 23, 2)
    for invalid_hour in (-1, 24):
        try:
            is_hour_active(invalid_hour, 8, 17)
            raise AssertionError('expected ValueError for out-of-range hour')
        except ValueError:
            pass


def validate_config() -> tuple[dict[str, object] | None, list[str]]:
    errors: list[str] = []

    def record(name: str, *, default=None, required: bool = False, validator=None):
        try:
            return get_env(name, default=default, required=required, validator=validator)
        except ValueError as exc:
            errors.append(str(exc))
            return default

    fbdev = record('FB_DEVICE', default=FBDEV)
    host = record('PIHOLE_HOST', default='127.0.0.1')
    scheme = record('PIHOLE_SCHEME', default='', validator=_parse_scheme)
    verify_tls = record('PIHOLE_VERIFY_TLS', default='auto', validator=_parse_verify_tls)
    ca_bundle = record('PIHOLE_CA_BUNDLE', default='')
    password = record('PIHOLE_PASSWORD', default='')
    api_token = record('PIHOLE_API_TOKEN', default='')
    refresh_secs = record('REFRESH_SECS', default=REFRESH_SECS, validator=_parse_int)
    request_timeout = record('PIHOLE_TIMEOUT', default=REQUEST_TIMEOUT, validator=_parse_float)
    active_hours = record('ACTIVE_HOURS', default=f'{ACTIVE_HOURS[0]},{ACTIVE_HOURS[1]}', validator=_parse_active_hours)

    if isinstance(refresh_secs, int) and refresh_secs < 1:
        errors.append('REFRESH_SECS is invalid: must be greater than or equal to 1')
    if isinstance(request_timeout, float) and request_timeout <= 0:
        errors.append('PIHOLE_TIMEOUT is invalid: must be greater than 0')
    if ca_bundle and not Path(str(ca_bundle)).is_file():
        errors.append('PIHOLE_CA_BUNDLE is invalid: file does not exist')
    if _host_requires_explicit_scheme(str(host)) and not str(scheme):
        errors.append(
            'Remote PIHOLE_HOST requires an explicit scheme: set PIHOLE_SCHEME=http|https or include http:// / https:// in PIHOLE_HOST'
        )

    auth_mode = detect_auth_mode(str(password), str(api_token))
    if auth_mode is None:
        errors.append(
            'Auth configuration is invalid: set PIHOLE_PASSWORD for v6 session auth or PIHOLE_API_TOKEN for legacy token auth'
        )

    if errors:
        return None, errors

    return {
        'fbdev': str(fbdev),
        'pihole_host': str(host),
        'pihole_scheme': str(scheme),
        'pihole_verify_tls': str(verify_tls),
        'pihole_ca_bundle': str(ca_bundle),
        'pihole_password': str(password),
        'pihole_api_token': str(api_token),
        'pihole_auth_mode': auth_mode,
        'request_timeout': float(request_timeout),
        'refresh_secs': int(refresh_secs),
        'active_hours': active_hours if isinstance(active_hours, tuple) else ACTIVE_HOURS,
    }, []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Pi-hole framebuffer dashboard')
    parser.add_argument('--check-config', action='store_true', help='Validate env configuration and exit')
    parser.add_argument('--self-test', action='store_true', help='Run active-hours self checks and exit')
    parser.add_argument('--diagnose-api', action='store_true', help='Print raw and normalized Pi-hole stats payload and exit')
    parser.add_argument('--output-image', default='', help='Write rendered frame to a PNG file instead of framebuffer')
    return parser.parse_args()


def apply_config(config: dict[str, object], output_image: str = '') -> None:
    global FBDEV, PIHOLE_HOST, PIHOLE_SCHEME, PIHOLE_VERIFY_TLS, PIHOLE_CA_BUNDLE
    global PIHOLE_PASSWORD, PIHOLE_API_TOKEN, PIHOLE_AUTH_MODE, REFRESH_SECS, ACTIVE_HOURS, REQUEST_TIMEOUT
    global OUTPUT_IMAGE, PIHOLE_CLIENT
    FBDEV = str(config['fbdev'])
    PIHOLE_HOST = str(config['pihole_host'])
    PIHOLE_SCHEME = str(config['pihole_scheme'])
    PIHOLE_VERIFY_TLS = str(config['pihole_verify_tls'])
    PIHOLE_CA_BUNDLE = str(config['pihole_ca_bundle'])
    PIHOLE_PASSWORD = str(config['pihole_password'])
    PIHOLE_API_TOKEN = str(config['pihole_api_token'])
    PIHOLE_AUTH_MODE = str(config['pihole_auth_mode'])
    REQUEST_TIMEOUT = float(config['request_timeout'])
    REFRESH_SECS = int(config['refresh_secs'])
    ACTIVE_HOURS = config['active_hours']
    OUTPUT_IMAGE = output_image.strip() or str(get_env('OUTPUT_IMAGE', default='')).strip()
    PIHOLE_CLIENT = PiHoleClient(
        host=PIHOLE_HOST,
        scheme=PIHOLE_SCHEME,
        verify_tls=PIHOLE_VERIFY_TLS,
        ca_bundle=PIHOLE_CA_BUNDLE,
        password=PIHOLE_PASSWORD,
        api_token=PIHOLE_API_TOKEN,
        request_timeout=REQUEST_TIMEOUT,
    )


def load_font(size: int, bold: bool = False):
    candidates = [
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        ('/usr/share/fonts/truetype/freefont/FreeSansBold.ttf' if bold else '/usr/share/fonts/truetype/freefont/FreeSans.ttf'),
        ('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'),
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    return x1 - x0, y1 - y0


def rgb888_to_rgb565(img_rgb: Image.Image) -> bytes:
    r, g, b = img_rgb.split()
    r = r.point(lambda value: value >> 3)
    g = g.point(lambda value: value >> 2)
    b = b.point(lambda value: value >> 3)
    payload = bytearray()
    rp = r.tobytes()
    gp = g.tobytes()
    bp = b.tobytes()
    for idx in range(len(rp)):
        value = ((rp[idx] & 0x1F) << 11) | ((gp[idx] & 0x3F) << 5) | (bp[idx] & 0x1F)
        payload += struct.pack('<H', value)
    return bytes(payload)


def _is_transient_io_error(exc: OSError) -> bool:
    return exc.errno in {errno.EAGAIN, errno.EINTR, errno.EBUSY, errno.ETIMEDOUT, errno.EIO}


def _retry_io(action, description: str, retries: int = IO_RETRIES):
    attempt = 0
    while True:
        try:
            return action()
        except OSError as exc:
            if attempt >= retries or not _is_transient_io_error(exc):
                raise RuntimeError(f'{description} failed after {attempt + 1} attempt(s): {exc}') from exc
            attempt += 1
            time.sleep(IO_RETRY_DELAY_SECS)


def _write_framebuffer_payload(payload: bytes) -> None:
    fb_file = None
    fb_map = None
    try:
        fb_file = open(FBDEV, 'r+b', buffering=0)
        fb_map = mmap.mmap(fb_file.fileno(), W * H * 2, mmap.MAP_SHARED, mmap.PROT_WRITE)
        fb_map.seek(0)
        fb_map.write(payload)
    finally:
        if fb_map is not None:
            fb_map.close()
        if fb_file is not None:
            fb_file.close()


def fb_write(img: Image.Image) -> None:
    if img.size != (W, H):
        img = img.resize((W, H), Image.BILINEAR)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    if OUTPUT_IMAGE:
        output_path = Path(OUTPUT_IMAGE)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _retry_io(lambda: img.save(output_path, format='PNG'), f'Writing PNG output image {output_path}')
        return
    payload = rgb888_to_rgb565(img)
    _retry_io(lambda: _write_framebuffer_payload(payload), f'Framebuffer write to {FBDEV}')


def read_temp_c() -> float | None:
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', encoding='utf-8') as handle:
            return int(handle.read().strip()) / 1000.0
    except Exception:
        return None


def read_uptime_str() -> str:
    try:
        with open('/proc/uptime', encoding='utf-8') as handle:
            secs = float(handle.read().split()[0])
        days = int(secs // 86400)
        secs -= days * 86400
        hours = int(secs // 3600)
        secs -= hours * 3600
        minutes = int(secs // 60)
        return f'{days}d {hours:02d}:{minutes:02d}' if days else f'{hours:02d}:{minutes:02d}'
    except Exception:
        return 'N/A'


def fetch_pihole() -> dict[str, object]:
    if PIHOLE_CLIENT is None:
        raise RuntimeError('Pi-hole client not configured')
    return PIHOLE_CLIENT.fetch()


def diagnose_api() -> dict[str, object]:
    if PIHOLE_CLIENT is None:
        raise RuntimeError('Pi-hole client not configured')
    return PIHOLE_CLIENT.diagnose()


def draw_temp_value(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], temp_c: float | None, font, colour: tuple[int, int, int]) -> None:
    if temp_c is None:
        text = 'N/A'
        width, height = text_size(draw, text, font)
        draw.text((rect[0] + (rect[2] - width) // 2, rect[1] + (rect[3] - height) // 2), text, font=font, fill=colour)
        return
    text = f'{temp_c:0.1f} C'
    width, height = text_size(draw, text, font)
    x = rect[0] + (rect[2] - width) // 2
    y = rect[1] + (rect[3] - height) // 2
    draw.text((x, y), text, font=font, fill=colour)


def draw_frame(stats: dict[str, object], temp_c: float | None, uptime: str, active: bool) -> Image.Image:
    img = Image.new('RGB', (W, H), COL_BG)
    draw = ImageDraw.Draw(img)
    big = load_font(28, True)
    mid = load_font(22, True)
    small = load_font(14, False)

    margin = 8
    tile_w = (W - margin * 3) // 2
    tile_h = (H - margin * 4) // 3
    y1 = margin
    y2 = margin * 2 + tile_h
    y3 = margin * 3 + tile_h * 2

    def tile(x: int, y: int, color: tuple[int, int, int], title: str, value, val_font, *, value_is_temp: bool = False) -> None:
        rect = (x, y, tile_w, tile_h)
        draw.rounded_rectangle([rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]], radius=12, fill=color)
        title_w, _ = text_size(draw, title, small)
        draw.text((rect[0] + (rect[2] - title_w) // 2, rect[1] + 6), title, font=small, fill=COL_TXT)
        if value_is_temp:
            draw_temp_value(draw, rect, value, val_font, COL_TXT)
            return
        value_w, value_h = text_size(draw, str(value), val_font)
        draw.text((rect[0] + (rect[2] - value_w) // 2, rect[1] + (rect[3] - value_h) // 2), str(value), font=val_font, fill=COL_TXT)

    if not active:
        draw.rounded_rectangle([margin, margin, W - margin, H - margin], radius=12, fill=(20, 20, 20))
        message = f'{TITLE}: Sleeping'
        width, height = text_size(draw, message, mid)
        draw.text(((W - width) // 2, (H - height) // 2), message, font=mid, fill=(180, 180, 180))
        return img

    total = int(stats['total'])
    blocked = int(stats['blocked'])
    percent = float(stats['percent']) if total > 0 else 0.0

    tile(margin, y1, COL_OK, 'TOTAL', f'{total:,}', big)
    tile(margin * 2 + tile_w, y1, COL_BAD, 'BLOCKED', f'{blocked:,}', big)
    tile(margin, y2, COL_MIX, '% BLOCKED', f'{percent:0.1f}%', big)
    tile(margin * 2 + tile_w, y2, COL_TEMP, 'TEMP', temp_c, big, value_is_temp=True)

    draw.rounded_rectangle([margin, y3, W - margin, y3 + tile_h], radius=12, fill=COL_UP)
    line1 = f'Uptime: {uptime}'
    failure = stats.get('failure', {}) if isinstance(stats.get('failure'), dict) else {}
    failure_reason = str(failure.get('reason', '')).strip()
    status = failure_reason if failure_reason else str(stats.get('status', 'OK' if stats.get('ok') else 'N/A'))
    line2 = f"{TITLE} {status}  |  {datetime.now().strftime('%H:%M')}"
    width1, height1 = text_size(draw, line1, mid)
    width2, _ = text_size(draw, line2, mid)
    cy = y3 + tile_h // 2
    draw.text((margin + (W - 2 * margin - width1) // 2, cy - height1 - 2), line1, font=mid, fill=COL_TXT)
    draw.text((margin + (W - 2 * margin - width2) // 2, cy + 2), line2, font=mid, fill=COL_TXT)
    return img


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_checks()
        print(f'[{SCRIPT_NAME}] Self checks passed.')
        return 0

    load_dotenv(DEFAULT_ROOT / '.env')
    config, errors = validate_config()
    if errors:
        report_validation_errors(SCRIPT_NAME, errors)
        return 1
    assert config is not None

    if args.check_config:
        print(f'[{SCRIPT_NAME}] Configuration check passed.')
        return 0

    apply_config(config, output_image=args.output_image)

    if args.diagnose_api:
        try:
            print(json.dumps(diagnose_api(), indent=2))
            return 0
        except Exception as exc:
            print(f'[{SCRIPT_NAME}] API diagnostic failed: {exc}', file=sys.stderr)
            return 1

    if not OUTPUT_IMAGE and not Path(FBDEV).exists():
        print(f'Framebuffer {FBDEV} not found.', file=sys.stderr)
        return 1

    cached: dict[str, object] = {'total': 0, 'blocked': 0, 'percent': 0.0, 'ok': False, 'status': 'INIT'}

    while True:
        hour = time.localtime().tm_hour
        active = is_hour_active(hour, ACTIVE_HOURS[0], ACTIVE_HOURS[1])
        stats = fetch_pihole()
        if stats['ok']:
            cached = stats
        else:
            cached = {**cached, **{k: v for k, v in stats.items() if k in {'ok', 'status', 'failure', 'source'}}}
        frame = draw_frame(cached, read_temp_c(), read_uptime_str(), active)
        fb_write(frame)
        if OUTPUT_IMAGE:
            print(f'[{SCRIPT_NAME}] Rendered test frame to {OUTPUT_IMAGE}.')
            return 0
        time.sleep(REFRESH_SECS)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass


