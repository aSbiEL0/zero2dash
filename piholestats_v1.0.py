#!/usr/bin/env python3
# Pi-hole TFT Dashboard -> direct framebuffer RGB565 (no X, no SDL)
# v6 auth handled elsewhere; this file only renders and calls API

import os, sys, time, json, urllib.request, urllib.parse, mmap, struct
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# -------- CONFIG --------
FBDEV = "/dev/fb1"
W, H = 320, 240
REFRESH_SECS = 10
ACTIVE_HOURS = (8, 23)

PIHOLE_HOST = "192.168.31.16"
PIHOLE_PASSWORD = "Unf0rg1v3n2"   # not used directly here; kept for context
TITLE = "Pi-hole"
# Colours
COL_BG   = (0, 0, 0)
COL_TXT  = (230,230,230)
COL_OK   = (0,120,255)
COL_BAD  = (255,64,64)
COL_MIX  = (255,170,0)
COL_TEMP = (0,200,120)
COL_UP   = (160,90,255)
# ------------------------

_SID = None
_SID_EXP = 0.0

# ---------- utils ----------
def load_font(size, bold=False):
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
         else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold
         else "/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
         else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()

def text_size(draw, text, font):
    x0, y0, x1, y1 = draw.textbbox((0,0), text, font=font)
    return x1 - x0, y1 - y0

def rgb888_to_rgb565(img_rgb):
    r, g, b = img_rgb.split()
    r = r.point(lambda i: i >> 3)
    g = g.point(lambda i: i >> 2)
    b = b.point(lambda i: i >> 3)
    arr = bytearray()
    rp = r.tobytes(); gp = g.tobytes(); bp = b.tobytes()
    for i in range(len(rp)):
        v = ((rp[i] & 0x1F) << 11) | ((gp[i] & 0x3F) << 5) | (bp[i] & 0x1F)
        arr += struct.pack("<H", v)
    return bytes(arr)

def fb_write(img):
    if img.size != (W, H):
        img = img.resize((W, H), Image.BILINEAR)
    if img.mode != "RGB":
        img = img.convert("RGB")
    payload = rgb888_to_rgb565(img)
    with open(FBDEV, "r+b", buffering=0) as f:
        mm = mmap.mmap(f.fileno(), W*H*2, mmap.MAP_SHARED, mmap.PROT_WRITE)
        mm.seek(0); mm.write(payload); mm.close()

def read_temp_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None

def read_uptime_str():
    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
        d = int(secs // 86400); secs -= d*86400
        h = int(secs // 3600);  secs -= h*3600
        m = int(secs // 60);    s = int(secs - m*60)
        return (f"{d}d {h:02d}:{m:02d}" if d else f"{h:02d}:{m:02d}")
    except Exception:
        return "N/A"

# ---------- Pi-hole v6 auth + fetch ----------
def _http_json(url, method="GET", body=None, timeout=3):
    headers = {"Content-Type": "application/json"} if body is not None else {}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def _auth_get_sid():
    global _SID, _SID_EXP
    js = _http_json(f"http://{PIHOLE_HOST}/api/auth", method="POST",
                    body={"password": PIHOLE_PASSWORD}, timeout=4)
    sess = js.get("session", {})
    if not sess.get("valid", False):
        raise RuntimeError("Auth failed")
    _SID = sess["sid"]
    _SID_EXP = time.time() + int(sess.get("validity", 1800)) - 10
    return _SID

def _ensure_sid():
    if _SID and time.time() < _SID_EXP:
        return _SID
    return _auth_get_sid()

def fetch_pihole():
    try:
        sid = _ensure_sid()
        url = f"http://{PIHOLE_HOST}/api/stats/summary?sid=" + urllib.parse.quote(sid, safe="")
        d = _http_json(url, timeout=4)
        if d.get("session", {}).get("valid") is False:
            sid = _auth_get_sid()
            url = f"http://{PIHOLE_HOST}/api/stats/summary?sid=" + urllib.parse.quote(sid, safe="")
            d = _http_json(url, timeout=4)
        q = d.get("queries", {})
        return {
            "total":   int(q.get("total", 0)),
            "blocked": int(q.get("blocked", 0)),
            "percent": float(q.get("percent_blocked", 0.0)),
            "ok": True
        }
    except Exception:
        return {"total":0,"blocked":0,"percent":0.0,"ok":False}

# ---------- rendering ----------
def draw_degree_circle(d, x, y, r, colour):
    # draw smooth small degree mark with no leftover black box
    bbox = (x - r, y - r, x + r, y + r)
    d.ellipse(bbox, fill=colour, outline=colour)

def draw_temp_value(d, rect, temp_c, font, colour):
    if temp_c is None:
        text = "N/A"
        tw, th = text_size(d, text, font)
        d.text((rect[0] + (rect[2]-tw)//2, rect[1] + (rect[3]-th)//2),
               text, font=font, fill=colour)
        return
    # Render "39.7 C" with no degree circle
    num = f"{temp_c:0.1f} C"
    tw, th = text_size(d, num, font)
    x = rect[0] + (rect[2]-tw)//2
    y = rect[1] + (rect[3]-th)//2
    d.text((x, y), num, font=font, fill=colour)


def draw_frame(stats, temp_c, uptime, active):
    img = Image.new("RGB", (W, H), COL_BG)
    d = ImageDraw.Draw(img)
    big   = load_font(28, True)
    mid   = load_font(22, True)   # slightly larger purple block font
    small = load_font(14, False)

    margin = 8
    tile_w = (W - margin*3) // 2
    tile_h = (H - margin*4) // 3
    y1 = margin
    y2 = margin*2 + tile_h
    y3 = margin*3 + tile_h*2

    def tile(x, y, color, title, value, val_font, value_is_temp=False):
        r = (x, y, tile_w, tile_h)
        d.rounded_rectangle([r[0],r[1],r[0]+r[2],r[1]+r[3]], radius=12, fill=color)
        tw, th = text_size(d, title, small)
        d.text((r[0]+(r[2]-tw)//2, r[1]+6), title, font=small, fill=COL_TXT)
        if value_is_temp:
            draw_temp_value(d, r, value, val_font, COL_TXT)
        else:
            tw, th = text_size(d, value, val_font)
            d.text((r[0]+(r[2]-tw)//2, r[1]+(r[3]-th)//2), value, font=val_font, fill=COL_TXT)

    if not active:
        d.rounded_rectangle([margin, margin, W-margin, H-margin], radius=12, fill=(20,20,20))
        msg = f"{TITLE}: Sleeping"
        tw, th = text_size(d, mid)
        d.text(((W-tw)//2,(H-th)//2), msg, font=mid, fill=(180,180,180))
        return img

    total   = stats["total"]
    blocked = stats["blocked"]
    percent = stats["percent"] if total>0 else 0.0

    tile(margin,           y1, COL_OK,   "TOTAL",     f"{total:,}",   big)
    tile(margin*2+tile_w,  y1, COL_BAD,  "BLOCKED",   f"{blocked:,}", big)
    tile(margin,           y2, COL_MIX,  "% BLOCKED", f"{percent:0.1f}%", big)
    tile(margin*2+tile_w,  y2, COL_TEMP, "TEMP",      temp_c,         big, value_is_temp=True)

    # Footer card: larger font for readability
    d.rounded_rectangle([margin, y3, W-margin, y3+tile_h], radius=12, fill=COL_UP)
    line1 = f"Uptime: {uptime}"
    line2 = f"{TITLE} {'OK' if stats['ok'] else 'N/A'}  |  {datetime.now().strftime('%H:%M')}"
    tw1, th1 = text_size(d, line1, mid)
    tw2, th2 = text_size(d, line2, mid)
    cy = y3 + tile_h//2
    d.text((margin + (W-2*margin - tw1)//2, cy - th1 - 2), line1, font=mid, fill=COL_TXT)
    d.text((margin + (W-2*margin - tw2)//2, cy + 2),       line2, font=mid, fill=COL_TXT)

    return img

# ---------- main ----------
def main():
    if not Path(FBDEV).exists():
        print(f"Framebuffer {FBDEV} not found.", file=sys.stderr)
        sys.exit(1)

    cached = {"total":0,"blocked":0,"percent":0.0,"ok":False}
    try:
        _auth_get_sid()
    except Exception:
        pass

    while True:
        hr = time.localtime().tm_hour
        active = (ACTIVE_HOURS[0] <= hr <= ACTIVE_HOURS[1])

        s = fetch_pihole()
        if s["ok"]:
            cached = s

        temp_c = read_temp_c()
        uptime = read_uptime_str()

        frame = draw_frame(cached, temp_c, uptime, active)
        fb_write(frame)
        time.sleep(REFRESH_SECS)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
