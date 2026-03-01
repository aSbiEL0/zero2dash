Minimal framebuffer-based Pi-hole dashboard for Raspberry Pi (320×240 SPI TFT).

No X11
No SDL
Direct /dev/fb1 RGB565 rendering
Suggested project structure
zero2dash/
├── scripts/
│   ├── pihole-display-pre.sh
│   ├── piholestats_v1.0.py
│   ├── piholestats_v1.1.py
│   ├── piholestats_v1.2.py
│   └── test.py
├── systemd/
│   ├── display.service
│   ├── pihole-display-dark.service
│   ├── day.timer
│   └── night.timer
└── README.md
Requirements
Raspberry Pi OS (SPI enabled)
Python 3
Pillow
systemd
Install
1. Install TFT driver
sudo rm -rf LCD-show
git clone https://github.com/goodtft/LCD-show.git
cd LCD-show
sudo ./LCD24-show
Reboot → display active on /dev/fb1.

2. Install Python dependency
sudo apt install -y python3-pip python3-pil
3. Deploy project files
sudo mkdir -p /opt/zero2dash
sudo cp -r . /opt/zero2dash/
sudo chmod +x /opt/zero2dash/scripts/pihole-display-pre.sh
sudo chmod +x /opt/zero2dash/scripts/test.py
Configure
Create an environment file and keep secrets out of source control:

cp /opt/zero2dash/.env.example /opt/zero2dash/.env
chmod 600 /opt/zero2dash/.env

Edit `/opt/zero2dash/.env` and set:

PIHOLE_HOST
PIHOLE_PASSWORD
PIHOLE_API_TOKEN (optional; enables legacy /admin/api.php fallback)
REFRESH_SECS
ACTIVE_HOURS
Run via systemd
If you run scripts manually, load env vars first:

set -a
source /opt/zero2dash/.env
set +a

sudo cp /opt/zero2dash/systemd/display.service /etc/systemd/system/
sudo cp /opt/zero2dash/systemd/pihole-display-dark.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now display.service
Check logs:

A lightweight Pi‑hole dashboard designed for small TFT displays (320×240) on a Raspberry Pi. It renders directly to the framebuffer (`/dev/fb1`) without requiring X11 or SDL, making it ideal for headless setups. The project provides a set of dashboard scripts that display Pi‑hole statistics, CPU temperature and device uptime. A companion rotator script allows multiple dashboards to cycle on a timer with simple touch controls for navigation and screen power management.

## Features

- **Direct framebuffer rendering** – uses the Pillow library to draw RGB565 frames directly to `/dev/fb1` with no desktop environment or SDL dependency.
- **Rotating dashboards** – `display_rotator.py` scans a directory for dashboard scripts and cycles through them on a configurable interval.
- **Touch navigation** – taps on the left/right side of the screen move to the previous/next dashboard; double‑tapping turns the screen on or off.
- **Dark and day modes** – separate dashboard scripts and systemd services for day and night display profiles.
- **Systemd integration** – sample `*.service` and `*.timer` units to start the dashboards on boot and automatically switch between day and night modes.
- **Test mode** – a `test.py` script renders a placeholder image for quick verification without connecting to the Pi‑hole API.

## Requirements

- Raspberry Pi OS with SPI and the TFT display enabled
- Python 3
- [Pillow](https://python-pillow.org/) library
- `systemd` for service management
- Pi‑hole v6 API accessible over the network

## Installation

1. **Prepare the TFT display**

   ```sh
   sudo rm -rf LCD-show
   git clone https://github.com/goodtft/LCD-show.git
   cd LCD-show
   sudo ./LCD24-show
   # reboot to activate /dev/fb1
   ```

2. **Install dependencies**

   ```sh
   sudo apt update
   sudo apt install -y python3-pip python3-pil
   ```

3. **Deploy the application**

   ```sh
   sudo mkdir -p /opt/zero2dash
   sudo cp -r . /opt/zero2dash/
   sudo chmod +x /opt/zero2dash/scripts/pihole-display-pre.sh
   sudo chmod +x /opt/zero2dash/scripts/test.py
   ```

## Configuration

Edit `scripts/piholestats_v1.2.py` (or the version you use) to point at your Pi‑hole instance:

```python
PIHOLE_HOST = "192.168.0.x"      # address of your Pi‑hole
PIHOLE_PASSWORD = "your_password"  # Pi‑hole v6 admin password
REFRESH_SECS = 3                   # seconds between API updates
ACTIVE_HOURS = (22, 7)             # hours to run this dark mode dashboard
```

The `display_rotator.py` script uses environment variables to discover and control dashboards:

- `ROTATOR_PAGES_DIR` – directory containing dashboard scripts (default: `scripts`)
- `ROTATOR_PAGE_GLOB` – glob pattern for dashboard filenames (default: `piholestats_v*.py`)
- `ROTATOR_EXCLUDE_PATTERNS` – comma‑separated list of patterns to ignore (default: `piholestats_v1.2.py,calendash-api.py,calendash-img.py`)
- `ROTATOR_SECS` – seconds to show each page before rotating (minimum 5)
- `ROTATOR_TOUCH_WIDTH` – touch‑sensitive width threshold for navigation
- `ROTATOR_PAGES` – optional explicit comma‑separated list of scripts to rotate

To experiment locally without a framebuffer, run:

```sh
python3 scripts/test.py --output /tmp/test.png --no-framebuffer
```

## Running via systemd

Two service units are provided to run the dashboards:

- **Day display** (`display.service`) – launches `display_rotator.py` and cycles through dashboard pages. A `day.timer` can start this service at 07:00 each day.
- **Night display** (`pihole-display-dark.service`) – runs the dark‑mode dashboard script. A `night.timer` can start this service at 22:00 each night.

Copy the desired units into `/etc/systemd/system` and enable them:

```sh
sudo cp /opt/zero2dash/systemd/*.service /etc/systemd/system/
sudo cp /opt/zero2dash/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now display.service
sudo systemctl enable --now day.timer night.timer
```

Check logs with:

```sh
journalctl -u display.service -n 50 --no-pager
```

## Development

The project is written in Python with an emphasis on readability and minimal dependencies. Dashboard scripts follow a simple pattern: fetch data from the Pi‑hole API, draw onto a PIL `Image`, then write the frame to the framebuffer using the `rgb888_to_rgb565` helper. Additional dashboards can be created by following the structure in `scripts/piholestats_v1.2.py`.

## License

Default backgrounds are loaded from the `images/` directory.


Touch controls and static pages
- Single tap left/right changes page.
- Double tap toggles screen power: OFF blanks/powers down the panel output, ON restores panel output. The rotator and page scripts keep running in both states (falls back to `vcgencmd display_power` when framebuffer blanking is unsupported).
- Image-only scripts can exit immediately; the rotator now keeps each page on-screen for `ROTATOR_SECS` unless you tap to switch.

## Google Calendar image generator (`scripts/calendash-api.py`)

This script creates a daily 320×240 PNG summary of upcoming Google Calendar events. It is designed to run separately from the rotator so image generation work is done once at 06:00 instead of every page cycle.

### Install dependencies

```sh
python3 -m pip install google-api-python-client google-auth-oauthlib python-dotenv pillow pytz
```

### Configure

1. Copy and edit env file:

   ```sh
   cp .env.example .env
   chmod 600 .env
   ```

2. Set these variables in `.env`:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_CALENDAR_ID` (for personal calendar use `primary`)
   - `OUTPUT_PATH`
   - `BACKGROUND_IMAGE`
   - `ICON_IMAGE`
   - `TIMEZONE` (example: `Europe/London`)
   - `OAUTH_PORT` (optional, default `8080`)

3. Place your assets:
   - `BACKGROUND_IMAGE`: 320×240 background containing the Google Calendar logo/header.
   - `ICON_IMAGE`: small calendar icon used in each event row.

### First run (OAuth)

Before first run, in Google Cloud Console open your OAuth client and ensure this redirect URI is allowed (or your custom `OAUTH_PORT` equivalent):

```text
http://localhost:8080/
```

Run once manually to complete OAuth2 login (local server flow) and create `token.json` in the repo root. When prompted, open the printed `http://localhost:<port>/` URL in a browser on the same machine (or via SSH port forwarding), approve access, and wait for the terminal to confirm the token was saved:

```sh
python3 scripts/calendash-api.py
```

After first auth, future runs refresh tokens automatically and are suitable for headless cron execution.

### Daily cron at 06:00 (local time)

```cron
0 6 * * * cd /opt/zero2dash && /usr/bin/python3 /opt/zero2dash/scripts/calendash-api.py >> /var/log/calendash.log 2>&1
```

The script fetches events from **today 00:00** to **+3 calendar days 23:59**, retries API/network failures with exponential backoff, and writes either the event summary image, a no-events image, or an error image.

## Calendar split workflow (generator + image-only display)

Use two independent scripts to reduce steady-state CPU and memory use:

1. `scripts/calendash-api.py` (scheduled, e.g. 06:00)
   - Calls Google Calendar API
   - Renders `images/calendash.png`
2. `scripts/calendash-img.py` (runtime display script)
   - Displays the pre-rendered image
   - Waits for either a touch event or a timeout, then exits

Example:

```sh
python3 scripts/calendash-api.py
python3 scripts/calendash-img.py --timeout 30 --touch-device /dev/input/event0
```

If `--touch-device` does not exist, `calendash-img.py` safely falls back to timeout-only behavior.
