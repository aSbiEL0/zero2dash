# zero2dash

Framebuffer dashboard stack for a 320x240 SPI TFT on Raspberry Pi.

- Direct rendering to `/dev/fb1`
- No X11, Wayland, SDL, or browser runtime
- Page-specific code and assets live under `modules/`

## Runtime overview

| Unit | Purpose | Entrypoint |
| --- | --- | --- |
| `boot-selector.service` | Boot GIF, 4-quadrant menu, and day/night selector | `boot/boot_selector.py` |
| `display.service` | Daytime page rotator | `display_rotator.py` |
| `night.service` | Night blackout screen | `modules/blackout/blackout.py` |
| `currency-update.service` | Refresh GBP/PLN image | `modules/currency/currency-rate.py` |
| `tram.service` | Refresh cached Firswood tram timetable | `modules/trams/tram_gtfs_refresh.py` |
| `tram-alerts.service` | Refresh cached Bee Network tram alerts | `modules/trams/tram_alerts_refresh.py` |

## Repository structure

```text
zero2dash/
├── _config.py
├── display_rotator.py
├── modules.txt
├── pihole-display-pre.sh
├── modules/
│   ├── blackout/
│   │   ├── blackout.py
│   │   └── raspberry-pi-icon.png
│   ├── calendash/
│   │   ├── calendash-api.py
│   │   ├── calendash-bkg.png
│   │   ├── calendash-icon.png
│   │   ├── calendash.png
│   │   ├── display.py
│   │   └── display_impl.py
│   ├── currency/
│   │   ├── currency-bkg.png
│   │   ├── currency-rate.py
│   │   ├── currency.py
│   │   └── display.py
│   ├── photos/
│   │   ├── drive-sync.py
│   │   ├── photo-resize.py
│   │   ├── photos-shuffle.py
│   │   └── display.py
│   └── pihole/
│       ├── pihole-bkg.png
│       ├── pihole_api.py
│       ├── piholestats_manual.py
│       └── display.py
├── systemd/
│   ├── currency-update.service
│   ├── currency-update.timer
│   ├── day.timer
│   ├── display.service
│   ├── night.service
│   └── night.timer
├── cache/
├── docs/
├── photos/
├── requirements.txt
└── README.md
```

## Module ownership

- `modules/blackout/` owns the night blackout renderer and its icon asset.
- `modules/pihole/` owns the Pi-hole renderer, Pi-hole API helpers, and Pi-hole page background.
- `modules/calendash/` owns the calendar display script, calendar generator, and calendar assets/output PNG.
- `modules/currency/` owns the currency display script, scheduled refresh script, and currency assets/output PNG.
- `modules/photos/` owns the photo display script plus Drive sync and resize helpers for the photos workflow.
- Root-level files are shared runtime helpers used across modules and services.

## Requirements

- Raspberry Pi OS with SPI display support enabled
- Python 3.11+ recommended
- `python3-pip`
- systemd
- Working framebuffer device, normally `/dev/fb1`

Install Python dependencies:

```sh
python3 -m pip install -r requirements.txt
```

If Pillow build dependencies are missing on the Pi:

```sh
sudo apt update
sudo apt install -y python3-pip python3-pil libjpeg-dev zlib1g-dev
```

## Display driver install

Example for the common GoodTFT 2.4" SPI stack:

```sh
sudo rm -rf LCD-show
git clone https://github.com/goodtft/LCD-show.git
cd LCD-show
sudo ./LCD24-show
# reboot after the installer finishes
```

Confirm the framebuffer exists after reboot:

```sh
ls -l /dev/fb1
```

## Project install

```sh
git clone <your-repo-url> /home/pihole/zero2dash
cd /home/pihole/zero2dash
python3 -m pip install -r requirements.txt
chmod +x pihole-display-pre.sh
```

Create the runtime config file:

```sh
cp .env.example .env
chmod 600 .env
```

## Configuration

### Core display settings

Common environment variables:

- `FB_DEVICE` default: `/dev/fb1`
- `FB_WIDTH` default: `320`
- `FB_HEIGHT` default: `240`
- `ACTIVE_HOURS` for day/night timer control
- `BOOT_SELECTOR_MAIN_MENU_IMAGE` optional 4-quadrant menu asset, default `boot/mainmenu.png`
- `BOOT_SELECTOR_DAY_NIGHT_IMAGE` optional day/night chooser asset, default `boot/day-night.png`
- `BOOT_SELECTOR_SHUTDOWN_IMAGE` optional shutdown confirmation asset, default `boot/yes-no.png`
- `BOOT_SELECTOR_INFO_GIF` optional info GIF asset, default `boot/credits.gif`
- `BOOT_SELECTOR_SHUTDOWN_COMMAND` optional safe shutdown command override

### Pi-hole page

Required:

- `PIHOLE_HOST`
- `PIHOLE_PASSWORD` for v6 session auth, or `PIHOLE_API_TOKEN` for token auth

Optional:

- `PIHOLE_SCHEME`
- `PIHOLE_VERIFY_TLS`
- `PIHOLE_CA_BUNDLE`
- `PIHOLE_TIMEOUT`
- `REFRESH_SECS`
- `OUTPUT_IMAGE` for PNG output during testing

### Calendash

Required for Google Calendar rendering:

- `GOOGLE_CALENDAR_ID`
- `TIMEZONE`
- `GOOGLE_CALENDAR_CLIENT_ID` and `GOOGLE_CALENDAR_CLIENT_SECRET`
  or `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`

Optional:

- `GOOGLE_TOKEN_PATH`
- `BACKGROUND_IMAGE`
- `ICON_IMAGE`
- `OUTPUT_PATH`
- `OAUTH_PORT`
- `GOOGLE_AUTH_MODE`

Default generated output:

- `modules/calendash/calendash.png`

### Photos

Preferred source:

- `LOCAL_PHOTOS_DIR`

Optional Google Photos settings:

- `GOOGLE_PHOTOS_ALBUM_ID`
- `GOOGLE_PHOTOS_CLIENT_SECRETS_PATH`
- `GOOGLE_PHOTOS_CLIENT_ID`
- `GOOGLE_PHOTOS_CLIENT_SECRET`
- `GOOGLE_TOKEN_PATH_PHOTOS`
- `CACHE_DIR`
- `FALLBACK_IMAGE`
- `LOGO_PATH`

Google Photos notes:

- Use a Desktop OAuth client.
- If the Google app is still in testing, add the account as a test user.
- Loopback OAuth must complete on the same machine, or through SSH port forwarding.
- Personal/shared albums are unreliable for unattended use; `LOCAL_PHOTOS_DIR` is the practical primary source.

### Currency

Optional currency settings:

- `CURRENCY_OUTPUT_PATH`
- `CURRENCY_BACKGROUND_IMAGE`
- `CURRENCY_STATE_PATH`
- `CURRENCY_NBP_API_BASE`
- `CURRENCY_API_TIMEOUT`

Default generated output:

- `modules/currency/current-currency.png`


### Trams

Optional tram settings:

- `TRAM_GTFS_URL`
- `TRAM_GTFS_CACHE_PATH`
- `TRAM_GTFS_TIMEOUT`
- `TRAM_STOP_NAME`
- `TRAM_STOP_ID`
- `TRAM_DIRECTION_LABEL`
- `TRAM_TIMEZONE`
- `TRAM_TARGET_HEADSIGNS`
- `TRAM_ALERTS_URL`
- `TRAM_ALERTS_CACHE_PATH`
- `TRAM_ALERTS_TIMEOUT`
- `TRAM_FONT_PATH`
- `TRAM_FONT_PATH_BOLD`
- `TRAM_FONT_PATH_ITALIC`

Default tram cache files:

- `modules/trams/tram_timetable.json`
- `modules/trams/tram_alerts.json`

## Module order

The day rotator discovers pages from `modules/`.

Default order is controlled by `modules.txt`:

```text
pihole
calendash
currency
photos
trams
```

Optional environment overrides:

- `ROTATOR_MODULES_DIR`
- `ROTATOR_MODULE_ORDER_FILE`
- `ROTATOR_MODULE_ENTRYPOINT`
- `ROTATOR_PAGES`

## Systemd install

```sh
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now boot-selector.service
sudo systemctl enable --now day.timer night.timer currency-update.timer tram.timer tram-alerts.timer
```

## Operating the system

### Start or restart services

```sh
sudo systemctl restart display.service
sudo systemctl restart night.service
sudo systemctl restart currency-update.service
sudo systemctl restart tram.service
sudo systemctl restart tram-alerts.service
```

### Check status

```sh
systemctl status display.service --no-pager
systemctl status night.service --no-pager
systemctl status currency-update.service --no-pager
systemctl status tram.service --no-pager
systemctl status tram-alerts.service --no-pager
systemctl list-timers --all | grep -E 'day.timer|night.timer|currency-update.timer|tram.timer|tram-alerts.timer'
```

### View logs

```sh
journalctl -u display.service -n 50 --no-pager
journalctl -u night.service -n 50 --no-pager
journalctl -u currency-update.service -n 50 --no-pager
journalctl -u tram.service -n 50 --no-pager
journalctl -u tram-alerts.service -n 50 --no-pager
```

## Validation commands

Configuration checks:

```sh
python3 modules/calendash/calendash-api.py --check-config
python3 modules/photos/photos-shuffle.py --check-config
python3 modules/photos/drive-sync.py --check-config
python3 modules/photos/photo-resize.py --check-config
python3 modules/currency/currency-rate.py --check-config
python3 modules/pihole/piholestats_manual.py --check-config
python3 modules/trams/tram_gtfs_refresh.py --check-config
python3 modules/trams/tram_alerts_refresh.py --check-config
```

Useful dry-run or local-output checks:

```sh
python3 modules/photos/photos-shuffle.py --test
python3 modules/currency/currency.py --self-test
python3 modules/currency/currency-rate.py --self-test
python3 modules/pihole/piholestats_manual.py --output-image /tmp/pihole-test.png
python3 modules/calendash/display.py --output /tmp/calendash-display.png --no-framebuffer
python3 modules/trams/tram_gtfs_refresh.py --self-test
python3 modules/trams/tram_alerts_refresh.py --self-test
python3 modules/trams/display.py --output /tmp/trams-display.png --no-framebuffer --frames 1
```

## Photos workflow with Drive sync

If you manage photos through a shared Google Drive folder:

```sh
python3 modules/photos/drive-sync.py
python3 modules/photos/photo-resize.py
python3 modules/photos/photos-shuffle.py --test
```

## Notes

- `modules/blackout/blackout.py` uses `modules/blackout/raspberry-pi-icon.png`.
- `pihole-display-pre.sh` is used by boot, day, and night services.
- Put the boot animation GIF at `boot/startup.gif`, or override it with `BOOT_SELECTOR_GIF_PATH`.
- After the boot GIF the selector shows a 4-quadrant menu: top-left opens the day/night screen, top-right plays the info GIF, bottom-left is unused, and bottom-right opens shutdown confirmation.
- `--selector-image` now refers specifically to the day/night screen.
- By default the boot assets are `boot/mainmenu.png`, `boot/day-night.png`, `boot/yes-no.png`, and `boot/credits.gif`. You can override them through `BOOT_SELECTOR_MAIN_MENU_IMAGE`, `BOOT_SELECTOR_DAY_NIGHT_IMAGE` (or legacy `BOOT_SELECTOR_IMAGE_PATH`), `BOOT_SELECTOR_SHUTDOWN_IMAGE`, and `BOOT_SELECTOR_INFO_GIF`.
- On shutdown confirmation the selector draws a blank screen before running the shutdown command.
- The module directories are the source of truth for page-specific scripts and page-specific assets.







