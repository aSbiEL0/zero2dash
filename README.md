# zero2dash

Lightweight framebuffer dashboards for a 320×240 SPI TFT on Raspberry Pi.

- No X11/Wayland
- No SDL
- Direct rendering to `/dev/fb1` (RGB565)

## Canonical service names and script targets

Use the following names as the **source of truth** for systemd-managed runtime modes.

| Service name | Script target | Mode |
| --- | --- | --- |
| `display.service` | `display_rotator.py` | **Day rotator** (multi-page cycle, touch navigation) |
| `pihole-display-dark.service` | `scripts/piholestats_v1.2.py` | **Night dark mode** (single Pi-hole dashboard) |

### Compatibility table (service → script → mode)

| Service | Script path | Mode / status |
| --- | --- | --- |
| `display.service` | `/opt/zero2dash/display_rotator.py` | Canonical day mode |
| `pihole-display-dark.service` | `/opt/zero2dash/scripts/piholestats_v1.2.py` | Canonical night mode |
| `day-mode.service` | *(legacy alias; not shipped in this repo)* | Legacy naming; replace with `display.service` |
| `dark-mode.service` | *(legacy alias; not shipped in this repo)* | Legacy naming; replace with `pihole-display-dark.service` |

## Repository layout

```text
zero2dash/
├── display_rotator.py
├── scripts/
│   ├── pihole-display-pre.sh
│   ├── piholestats_v1.3.py      # always-on daytime variant
│   ├── piholestats_v1.2.py      # canonical dark-mode service target
│   ├── calendash-api.py
│   ├── calendash-img.py
│   ├── google-photos.py
│   ├── photos-shuffle.py
│   ├── tram-info.py
│   └── weather-dash.py
├── systemd/
│   ├── display.service
│   ├── pihole-display-dark.service
│   ├── day.timer
│   └── night.timer
└── README.md
```

## Stale / legacy references removed

- `scripts/piholestats_v1.0.py` and `scripts/test.py` are not part of this repository and should not be used in deployment docs.
- `day-mode.service` and `dark-mode.service` are treated as **legacy names** only.

## Requirements

- Raspberry Pi OS (SPI enabled)
- Python 3
- Pillow (`python3-pil`)
- systemd
- Pi-hole API connectivity

## Installation

```sh
sudo rm -rf LCD-show
git clone https://github.com/goodtft/LCD-show.git
cd LCD-show
sudo ./LCD24-show
# reboot to activate /dev/fb1
```

```sh
sudo apt update
sudo apt install -y python3-pip python3-pil
```

```sh
sudo mkdir -p /opt/zero2dash
sudo cp -r . /opt/zero2dash/
sudo chmod +x /opt/zero2dash/scripts/pihole-display-pre.sh
```

## Configuration

Create and secure an env file:

```sh
cp /opt/zero2dash/.env.example /opt/zero2dash/.env
chmod 600 /opt/zero2dash/.env
```

Set at minimum for Pi-hole:

- `PIHOLE_HOST`
- `PIHOLE_SCHEME` if `PIHOLE_HOST` is remote and does not already include `http://` or `https://`
- `PIHOLE_PASSWORD` for v6 session auth, or `PIHOLE_API_TOKEN` for legacy token auth
- `PIHOLE_VERIFY_TLS=false` for self-signed HTTPS, or `PIHOLE_CA_BUNDLE=/path/to/ca.pem` to verify a private CA
- `PIHOLE_TIMEOUT`
- `REFRESH_SECS`
- `ACTIVE_HOURS` (inclusive `start,end` hour window in 24h format; cross-midnight values like `22,7` are supported)

Google OAuth notes:

- Use Desktop OAuth clients for Calendar and Photos.
- Loopback OAuth only: complete sign-in on the same machine as the script, or tunnel the callback port from a headless Pi with `ssh -L 8080:localhost:8080 pihole@pihole`.
- If the Google consent screen is in testing, add your account as a test user.
- Enable Google Photos Library API in the same Google Cloud project as the Photos OAuth client.
- Since 31 March 2025, Google Photos Library API only exposes app-created albums/media. Personal or shared albums need a different source, such as a pre-populated local cache used by `photos-shuffle.py` when online fetch is unavailable.
- `calendash-api.py` defaults `GOOGLE_TOKEN_PATH` to `token.json` relative to `/opt/zero2dash` under systemd; `photos-shuffle.py` must keep using a separate `GOOGLE_TOKEN_PATH_PHOTOS`.
- For normal personal/shared albums, prefer `LOCAL_PHOTOS_DIR` plus `scripts/drive-sync.py` instead of Google Photos API.
- `scripts/photo-resize.py` resizes changed files in `LOCAL_PHOTOS_DIR` by 50% and is safe to run repeatedly because it tracks processed mtimes in `PHOTO_RESIZE_STATE_PATH`.

Drive-backed photos:

- Put display-ready local photos in `~/zero2dash/photos`, or sync them there with `scripts/drive-sync.py`.
- `drive-sync.py` reads `GOOGLE_DRIVE_FOLDER_ID` and `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`, downloads image files into `LOCAL_PHOTOS_DIR`, then runs `photo-resize.py`.
- Share the Drive folder directly with the service account email as `Viewer`. Do not rely on link-sharing if you want this to work without resource-key surprises.

## Run via systemd
Install and enable canonical units:

```sh
sudo cp /opt/zero2dash/systemd/*.service /etc/systemd/system/
sudo cp /opt/zero2dash/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now display.service
sudo systemctl enable --now day.timer night.timer
```

Useful checks:

```sh
journalctl -u display.service -n 50 --no-pager
journalctl -u pihole-display-dark.service -n 50 --no-pager
```

## Notes

- `display_rotator.py` excludes `piholestats_v1.2.py` by default so day mode and night mode stay distinct.
- Static image scripts (for example `tram-info.py`, `weather-dash.py`, `calendash-img.py`) are rotator-friendly page scripts, not systemd service units by themselves.




