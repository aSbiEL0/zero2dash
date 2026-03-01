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
- `ROTATOR_PAGE_GLOB` – glob pattern for dashboard filenames (default: `*.py`)
- `ROTATOR_EXCLUDE_PATTERNS` – comma‑separated list of patterns to ignore (default: `piholestats_v1.2.py,calendash-api.py`)
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
   - Optional: `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET` (dedicated Calendar OAuth client)
   - `GOOGLE_CALENDAR_ID` (for personal calendar use `primary`)
   - `OUTPUT_PATH` (recommended: `~/zero2dash/images/calendash.png`)
   - `BACKGROUND_IMAGE`
   - `ICON_IMAGE`
   - `CALENDASH_FONT_PATH` (optional comma-separated font file paths; first existing path is used)
   - `TIMEZONE` (example: `Europe/London`)
   - `OAUTH_PORT` (optional, default `8080`)

3. Place your assets:
   - `BACKGROUND_IMAGE`: 320×240 background containing the Google Calendar logo/header.
   - `ICON_IMAGE`: small calendar icon used in each event row.
   - `CALENDASH_FONT_PATH`: optional fallback list to try alternate fonts, e.g. `/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf,/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`.

### First run (OAuth)

Before first run, in Google Cloud Console open your OAuth client and ensure this redirect URI is allowed (replace `8080` if you set `OAUTH_PORT` differently):

```text
http://localhost:8080/
```

Run once manually to complete OAuth2 login (local server flow) and create `token.json` in the repo root. When prompted, open the printed `http://localhost:<port>/` URL in a browser on the same machine (or via SSH port forwarding), approve access, and wait for the terminal to confirm the token was saved:

```sh
python3 scripts/calendash-api.py
```

After first auth, future runs refresh tokens automatically and are suitable for headless cron execution.


### Token separation (important)

Use separate OAuth token files per script to avoid scope conflicts:

- `scripts/calendash-api.py` (Calendar): `GOOGLE_TOKEN_PATH` (default `token.json`)
- `scripts/photos-shuffle.py` (Photos): `GOOGLE_TOKEN_PATH_PHOTOS` (default `~/zero2dash/token_photos.json`)

Do **not** point the Photos script at `token.json`. The Photos script now blocks that configuration and asks for a separate token path.

If you see **"app restricted"** in browser consent, create **separate Desktop OAuth clients** in Google Cloud: one for Calendar and one for Photos. Then set:

- Calendar: `GOOGLE_CALENDAR_CLIENT_ID` / `GOOGLE_CALENDAR_CLIENT_SECRET`
- Photos: `GOOGLE_PHOTOS_CLIENT_ID` / `GOOGLE_PHOTOS_CLIENT_SECRET` (or `GOOGLE_PHOTOS_CLIENT_SECRETS_PATH`)

Also keep the consent screen in **Testing** and add your Google account as a **Test user**.

### OAuth troubleshooting (`localhost` connection refused after clicking **Continue**)

If Google sign-in works but the final redirect page fails with `localhost refused to connect`, the browser and `calendash-api.py` are usually not on the same network namespace.

- If script and browser are on the same machine, re-run the script and immediately open the exact URL it prints.
- If script runs on a remote Pi/VM over SSH and browser runs on your laptop, create an SSH tunnel before authorizing:

  ```sh
  ssh -L 8080:localhost:8080 <user>@<pi-or-server>
  ```

  Keep that SSH session open, then run `python3 scripts/calendash-api.py` on the remote host and complete Google consent from your local browser.

- Ensure `.env` `OAUTH_PORT` and Google OAuth redirect URI match exactly, including trailing slash:

  ```text
  http://localhost:8080/
  ```

- If port `8080` is already used, set another value for `OAUTH_PORT` (for example `8090`) and add the matching URI in Google Cloud Console.
- If you are using an SSH tunnel, a message like `channel 3: open failed: connect failed: Connection refused` can appear after consent when the browser makes an extra request (for example `/favicon.ico`) after the local OAuth server already shut down. If `Saved OAuth token...` and `Wrote image: ...` are logged, OAuth completed successfully.

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

`calendash-api.py` is excluded from rotator discovery by default because it is a generator, but `calendash-img.py` is **not** excluded so you can rotate it like any other display page.

Example:

```sh
python3 scripts/calendash-api.py
python3 scripts/calendash-img.py --timeout 30 --touch-device /dev/input/event0
```

If `--touch-device` does not exist, `calendash-img.py` safely falls back to timeout-only behavior.
