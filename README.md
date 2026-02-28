# Pi-hole SPI TFT Dashboard

[![Platform](https://img.shields.io/badge/Raspberry%20Pi-supported-C51A4A.svg)](https://www.raspberrypi.com/)
[![Render](https://img.shields.io/badge/render-%2Fdev%2Ffb1-informational.svg)](#)

Minimal framebuffer-based Pi-hole dashboard for Raspberry Pi (320×240 SPI TFT).

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

## Run via systemd

```bash
sudo cp pihole-display*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pihole-display.service
```

Check logs:

```bash
journalctl -u pihole-display.service -n 50 --no-pager
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
