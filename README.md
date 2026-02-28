# Pi-hole SPI TFT Dashboard

[![Platform](https://img.shields.io/badge/Raspberry%20Pi-supported-C51A4A.svg)](https://www.raspberrypi.com/)
[![Render](https://img.shields.io/badge/render-%2Fdev%2Ffb1-informational.svg)](#)

Framebuffer-based rotating dashboard for Raspberry Pi (320×240 SPI TFT), designed to run separate scripts as pages for different data sets (for example: weather, calendar, Pi-hole stats, RSS feeds, and more).

* No X11
* No SDL
* Direct `/dev/fb1` RGB565 rendering

---

## Requirements

* Raspberry Pi OS (SPI enabled)
* Python 3
* Pillow
* systemd

---

## Install

### 1. Install TFT driver

```bash
sudo rm -rf LCD-show
git clone https://github.com/goodtft/LCD-show.git
cd LCD-show
sudo ./LCD24-show
```

Reboot → display active on `/dev/fb1`.

---

### 2. Install Python dependency

```bash
sudo apt install -y python3-pip
pip3 install pillow
```

---

## Configure

Edit in `piholestats_v1.2.py`:

* `PIHOLE_HOST`
* `PIHOLE_PASSWORD`
* `REFRESH_SECS`

---

## Day mode page rotation

`display.service` starts `display_rotator.py`, which rotates independent page scripts so each page can show a different data set (weather, calendar, Pi-hole, RSS, etc.).

Touch controls in `display_rotator.py`:

* Tap right side — next page/script
* Tap left side — previous page/script
* Double tap anywhere — screen off/on

Optional environment variables for the rotator:

* `ROTATOR_PAGES` — comma-separated script list (default: `piholestats_v1.0.py,piholestats_v1.1.py`)
* `ROTATOR_SECS` — seconds per page (default: `30`, minimum: `5`)
* `ROTATOR_TOUCH_DEVICE` — explicit `/dev/input/eventX` device for touch input
* `ROTATOR_TOUCH_WIDTH` — touch X-axis width used to split left/right taps (default: `320`)
* `ROTATOR_FBDEV` — framebuffer device used for screen blank/unblank (default: `/dev/fb1`)

Example systemd override:

```bash
sudo systemctl edit display.service
```

Then add:

```ini
[Service]
Environment=ROTATOR_PAGES=piholestats_v1.0.py,piholestats_v1.1.py
Environment=ROTATOR_SECS=20
```

## Run via systemd

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now display.service
```

Check logs:

```bash
journalctl -u display.service -n 50 --no-pager
```

---

## Architecture

```text
SPI TFT → /dev/fb1 → Python → Pi-hole API
```

---

## Notes

* Shows: Total, Blocked, % Blocked, Temp, Uptime
* No hardware backlight control
* Touch not used in UI

---

Private project.
