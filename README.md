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

journalctl -u display.service -n 50 --no-pager
Placeholder test script
To verify basic rendering logic:

python3 /opt/zero2dash/scripts/test.py --fbdev /dev/fb1
Or generate a local preview without touching framebuffer:

python3 /opt/zero2dash/scripts/test.py --output /tmp/test.png --no-framebuffer
Architecture
SPI TFT → /dev/fb1 → Python → Pi-hole API
Notes
Shows: Total, Blocked, % Blocked, Temp, Uptime
No hardware backlight control
Touch not used in UI
Private project.

Display rotator configuration
`display_rotator.py` now supports directory-based page discovery so you do not need to list every script file manually.

Environment variables:
- `ROTATOR_PAGES_DIR` (default: `scripts`) → directory to scan for pages.
- `ROTATOR_PAGE_GLOB` (default: `*.py`) → file pattern(s) inside that directory. You can pass a comma-separated list such as `piholestats_v*.py,*-dash.py`.
- `ROTATOR_EXCLUDE_PATTERNS` (default: `piholestats_v1.2.py`) → comma-separated filename patterns to skip.
- `ROTATOR_PAGES` → optional legacy explicit page list override.

If you have a dark-mode script such as `pihole-display-dark_v1.2.py`, keep it outside the rotator pages directory or leave it in the directory and rely on `ROTATOR_EXCLUDE_PATTERNS`.

Image background test scripts
The repository now includes image-only page scripts that can be used while building rotator functionality:

- `scripts/weather-dash.py`
- `scripts/calendash.py`
- `scripts/google-photos.py`
- `scripts/tram-info.py`

Default backgrounds are loaded from the `images/` directory.


Touch controls and static pages
- Single tap left/right changes page.
- Double tap toggles screen power (falls back to `vcgencmd display_power` when framebuffer blanking is unsupported).
- Image-only scripts can exit immediately; the rotator now keeps each page on-screen for `ROTATOR_SECS` unless you tap to switch.
