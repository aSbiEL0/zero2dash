# zero2dash

Framebuffer dashboard stack for a 320x240 SPI TFT on Raspberry Pi.

- Direct rendering to `/dev/fb1`
- No X11, Wayland, SDL, or browser runtime
- Page-specific code and assets live under `modules/`

## Runtime overview

| Unit | Purpose | Entrypoint |
| --- | --- | --- |
| `boot-selector.service` | Primary shell runtime, paged app menu, child-app lifecycle owner | `boot/boot_selector.py` |
| `display.service` | Legacy/manual compatibility path for Dashboards | `display_rotator.py` |
| `night.service` | Legacy/manual compatibility path for Night blackout | `modules/blackout/blackout.py` |
| `shell-mode-switch@.service` | Shell mode request bridge for timers and operators | `boot/boot_selector.py --request-mode <mode>` |
| `currency-update.service` | Independent refresh job for the GBP/PLN image | `modules/currency/currency-rate.py` |
| `weather.service` | Independent refresh job for the weather image | `modules/weather/weather_refresh.py` |
| `tram.service` | Independent refresh job for the cached Firswood tram timetable | `modules/trams/tram_gtfs_refresh.py` |
| `tram-alerts.service` | Independent refresh job for the cached Bee Network tram alerts | `modules/trams/tram_alerts_refresh.py` |

## Rebuild status

- Active rebuild plan: `rebuild-plan.md`
- Completed slices: `R-001` rotator extraction, `R-002` framebuffer consolidation, `R-003` service boundary hardening
- `display_rotator.py` remains the supported Dashboards entrypoint
- `framebuffer.py` and `rotator/` are the shared internal runtime helpers
- Feature ideas live in `coordination/ideas.md` and remain out of scope unless promoted

## Repository structure

```text
zero2dash/
├── PLAN.md
├── rebuild-plan.md
├── coordination/
├── _config.py
├── display_rotator.py
├── framebuffer.py
├── modules.txt
├── pihole-display-pre.sh
├── rotator/
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
│   ├── currency/
│   │   ├── currency-bkg.png
│   │   ├── currency-rate.py
│   │   ├── currency.py
│   │   └── display.py
│   ├── weather/
│   │   ├── display.py
│   │   ├── weather-background.png
│   │   ├── weather-cache.json
│   │   ├── weather.png
│   │   └── weather_refresh.py
│   ├── photos/
│   │   ├── drive-sync.py
│   │   ├── photo-resize.py
│   │   ├── display.py
│   │   └── slideshow.py
│   └── pihole/
│       ├── pihole-bkg.png
│       ├── pihole_api.py
│       └── display.py
├── systemd/
│   ├── boot-selector.service
│   ├── currency-update.service
│   ├── currency-update.timer
│   ├── day.timer
│   ├── display.service
│   ├── night.service
│   ├── night.timer
│   ├── shell-mode-switch@.service
│   ├── weather.service
│   └── weather.timer
├── cache/
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
- `modules/weather/` owns the weather renderer, cached weather data, and generated weather image.
- Root-level files such as `_config.py`, `framebuffer.py`, and `rotator/` are shared runtime helpers used across modules and services.

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
- `BOOT_SELECTOR_SHUTDOWN_COMMAND` optional safe shutdown command override
- `BOOT_SELECTOR_MODE_REQUEST_PATH` optional shell mode request file override

## Shell-first runtime

The normal foreground runtime is now `boot-selector.service`.

- The shell owns the framebuffer during normal operation.
- Dashboards runs as a child app via `display_rotator.py`.
- Photos runs as a child app via `modules/photos/slideshow.py`.
- Refresh jobs like `weather.service`, `currency-update.service`, `tram.service`, and `tram-alerts.service` run independently and do not depend on the foreground shell service being active.
- `display.service` and `night.service` remain available as manual compatibility paths.
- `day.timer` and `night.timer` now target `shell-mode-switch@.service` instead of starting competing foreground UI services.
- The rebuild contract for mode switching is request-file based; the oneshot service is the bridge used by timers and operators.

Shell modes:

- `menu`
- `dashboards`
- `photos`
- `night`

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
- `OAUTH_PORT`
- `GOOGLE_AUTH_MODE`

Google Calendar notes:

- `GOOGLE_TOKEN_PATH` should point to a dedicated calendar token file.
- Use a Desktop OAuth client.
- If the Google app is still in testing, add the account as a test user.
- Loopback OAuth must complete on the same machine, or through SSH port forwarding.
- When the cached token expires or is revoked, refresh it manually on the Pi with `python3 modules/calendash/calendash-api.py --auth-only --auth-mode local_server`.
- For remote SSH sessions, forward the callback port first, for example `ssh -L 8080:localhost:8080 <user>@<pi-host>`.

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

Google Photos notes:

- Use a Desktop OAuth client.
- If the Google app is still in testing, add the account as a test user.
- Loopback OAuth must complete on the same machine, or through SSH port forwarding.
- Personal/shared albums are unreliable for unattended use; `LOCAL_PHOTOS_DIR` is the practical primary source.
- Bundled fallback assets stay in `modules/photos/` by default.
- Source selection order is: local, then online Google Photos, then offline cache, then bundled fallback image.
- `modules/photos/display.py` remains the one-shot renderer for compatibility.
- `modules/photos/slideshow.py` is the long-running shell-launched Photos app.

### Currency

Optional currency settings:

- `CURRENCY_NBP_API_BASE`
- `CURRENCY_API_TIMEOUT`

Default generated output:

- `modules/currency/current-currency.png`


### Weather

Required weather settings:

- `WEATHER_LAT`
- `WEATHER_LON`

Optional weather settings:

- `WEATHER_LABEL`
- `WEATHER_TIMEZONE`
- `WEATHER_API_TIMEOUT`
- `WEATHER_API_BASE`

Default weather output files:

- `modules/weather/weather.png`
- `modules/weather/weather-cache.json`

### Trams

Optional tram settings:

- `TRAM_GTFS_URL`
- `TRAM_GTFS_TIMEOUT`
- `TRAM_STOP_NAME`
- `TRAM_STOP_ID`
- `TRAM_DIRECTION_LABEL`
- `TRAM_TIMEZONE`
- `TRAM_TARGET_HEADSIGNS`
- `TRAM_ALERTS_URL`
- `TRAM_ALERTS_TIMEOUT`
- `TRAM_FONT_PATH`
- `TRAM_FONT_PATH_BOLD`
- `TRAM_FONT_PATH_ITALIC`

Default tram cache files:

- `modules/trams/tram_timetable.json`
- `modules/trams/tram_alerts.json`

## Module order

The Dashboards app discovers pages from `modules/`.

Default order is controlled by `modules.txt`:

```text
pihole
calendash
currency
weather
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
sudo systemctl enable --now day.timer night.timer currency-update.timer weather.timer tram.timer tram-alerts.timer
```

Optional manual compatibility services:

```sh
sudo systemctl enable display.service
sudo systemctl enable night.service
```

## Operating the system

### Start or restart services

```sh
sudo systemctl restart boot-selector.service
sudo systemctl restart display.service
sudo systemctl restart night.service
sudo systemctl restart currency-update.service
sudo systemctl restart weather.service
sudo systemctl restart tram.service
sudo systemctl restart tram-alerts.service
```

### Check status

```sh
systemctl status boot-selector.service --no-pager
systemctl status display.service --no-pager
systemctl status night.service --no-pager
systemctl status 'shell-mode-switch@*.service' --no-pager
systemctl status currency-update.service --no-pager
systemctl status weather.service --no-pager
systemctl status tram.service --no-pager
systemctl status tram-alerts.service --no-pager
systemctl list-timers --all | grep -E 'day.timer|night.timer|currency-update.timer|weather.timer|tram.timer|tram-alerts.timer'
```

### View logs

```sh
journalctl -u boot-selector.service -n 50 --no-pager
journalctl -u display.service -n 50 --no-pager
journalctl -u night.service -n 50 --no-pager
journalctl -u 'shell-mode-switch@*.service' -n 20 --no-pager
journalctl -u currency-update.service -n 50 --no-pager
journalctl -u weather.service -n 50 --no-pager
journalctl -u tram.service -n 50 --no-pager
journalctl -u tram-alerts.service -n 50 --no-pager
```

## Validation matrix

| Scope | Command | Notes |
| --- | --- | --- |
| Shell contracts | `python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif` | Confirms the shell registry and mode surface stay intact. |
| Rotator slice | `python3 -m unittest tests.test_display_rotator` | Covers the extracted touch and screen-power paths. |
| Framebuffer slice | `python3 -m unittest tests.test_framebuffer` | Covers RGB565 conversion and framebuffer writes. |
| Shell smoke | `python3 boot/boot_selector.py --no-framebuffer --skip-gif` | Verifies the shell boots without hardware writes. |
| Module configs | `python3 modules/calendash/calendash-api.py --check-config` and the equivalent `--check-config` checks for photos, weather, Pi-hole, and trams refresh scripts | Confirms script-level config parsing before runtime. |
| Module self-tests | `python3 modules/photos/slideshow.py --self-test` and `python3 modules/weather/weather_refresh.py --self-test` | Confirms long-running child and refresh helpers still behave. |
| Pi-hole render | `python3 modules/pihole/display.py --output-image /tmp/pihole-test.png` | Checks a representative image-producing module. |
| Trams render | `python3 modules/trams/display.py --output /tmp/trams-display.png --no-framebuffer --frames 1` | Checks framebuffer output without hardware writes. |

## Photos workflow with Drive sync

If you manage photos through a shared Google Drive folder:

```sh
python3 modules/photos/drive-sync.py
python3 modules/photos/photo-resize.py
python3 modules/photos/display.py --test
python3 modules/photos/slideshow.py --self-test
```

## Pi live test checklist

Use this sequence on the Pi after deploying the repo and installing dependencies:

```sh
cd /home/pihole/zero2dash
python3 -m pip install -r requirements.txt
python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif
python3 modules/photos/slideshow.py --check-config
python3 modules/photos/slideshow.py --self-test
python3 display_rotator.py --list-pages
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart boot-selector.service
systemctl status boot-selector.service --no-pager
systemctl list-timers --all | grep -E 'day.timer|night.timer'
```

Manual runtime smoke checks on the Pi:

- Confirm the shell boots to the paged menu.
- Launch Dashboards from the shell and verify Photos is not in the rotator.
- Launch Photos from the shell and verify automatic slide advance.
- Hold the reserved Home corner and confirm the shell reclaims control.
- Request shell modes explicitly with `python3 boot/boot_selector.py --request-mode dashboards`, `photos`, `night`, and `menu`.
- Confirm `weather.service` can run without `display.service` being active.
- Verify `day.timer` switches to Dashboards and `night.timer` switches to Night without starting a competing foreground service.
- Confirm `display.service` and `night.service` still work as manual compatibility paths when invoked directly.

## Remaining Risks

- Final Pi validation is still required for touch, framebuffer, and service behavior that cannot be proven on a non-hardware host.
- `display.service` and `night.service` remain compatibility paths, not the primary runtime.
- Feature ideas in `coordination/ideas.md` are backlog only until Merlin promotes them.

## Notes

- `modules/blackout/blackout.py` uses `modules/blackout/raspberry-pi-icon.png`.
- `pihole-display-pre.sh` is used by boot, day, and night services.
- Put the boot animation GIF at `boot/startup.gif`, or override it with `BOOT_SELECTOR_GIF_PATH`.
- After the boot GIF the shell shows a paged 4-tile menu for Dashboards, Photos, Info GIF, keypad, and shutdown.
- `--selector-image` is used as the Dashboards preview asset in the shell menu.
- By default the boot assets are `boot/mainmenu.png`, `boot/day-night.png`, `boot/yes-no.png`, `boot/keypad.png`, and `boot/credits.gif`. Treat those as bundled application assets, not routine `.env` settings.
- The keypad expects a PIN from `BOOT_SELECTOR_PIN`; a correct PIN runs `/home/pihole/player.sh`, and three consecutive wrong PIN submissions shut the Pi down via `BOOT_SELECTOR_SHUTDOWN_COMMAND`.
- On shutdown confirmation the selector draws a blank screen before running the shutdown command.
- The module directories are the source of truth for page-specific scripts and page-specific assets.





