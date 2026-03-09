# zero2dash

Lightweight framebuffer dashboards for a 320x240 SPI TFT on Raspberry Pi.

- No X11 or Wayland
- No SDL
- Direct rendering to `/dev/fb1` (RGB565)

## Canonical runtime targets

Use these names as the source of truth for systemd-managed modes.

| Service name | Script target | Mode |
| --- | --- | --- |
| `display.service` | `display_rotator.py` | Day rotator (multi-page cycle, touch navigation) |
| `pihole-display-dark.service` | `scripts/piholestats_v1.2.py` | Night dark mode (single Pi-hole dashboard) |

### Pi-hole script variants

| Script | Status | Purpose |
| --- | --- | --- |
| `scripts/piholestats_v1.2.py` | Canonical | Night-mode service target |
| `scripts/piholestats_v1.3.py` | Current manual variant | Always-on Pi-hole stats display |
| `scripts/piholestats_v1.1.py` | Legacy compatibility | Older daytime variant with shared API diagnostics |

### Compatibility table

| Runtime entry point | Target | Status |
| --- | --- | --- |
| `display.service` | `/opt/zero2dash/display_rotator.py` | Canonical day mode |
| `pihole-display-dark.service` | `/opt/zero2dash/scripts/piholestats_v1.2.py` | Canonical night mode |
| `scripts/piholestats_v1.3.py` | Manual launch only | Always-on Pi-hole display |
| `day-mode.service` | Not shipped in this repo | Legacy naming only |
| `dark-mode.service` | Not shipped in this repo | Legacy naming only |

## Repository layout

```text
zero2dash/
|-- display_rotator.py
|-- scripts/
|   |-- _config.py
|   |-- pihole_api.py
|   |-- pihole-display-pre.sh
|   |-- piholestats_v1.1.py
|   |-- piholestats_v1.2.py
|   |-- piholestats_v1.3.py
|   |-- calendash-api.py
|   |-- calendash-img.py
|   |-- photos-shuffle.py
|   |-- drive-sync.py
|   |-- photo-resize.py
|-- systemd/
|   |-- display.service
|   |-- pihole-display-dark.service
|   |-- day.timer
|   |-- night.timer
`-- README.md
```

## Requirements

- Raspberry Pi OS with SPI enabled
- Python 3
- Pillow (`python3-pil`)
- `python-dotenv`
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
pip3 install -r requirements.txt
```

```sh
sudo mkdir -p /opt/zero2dash
sudo cp -r . /opt/zero2dash/
sudo chmod +x /opt/zero2dash/scripts/pihole-display-pre.sh
```

## Configuration

Create and secure the env file:

```sh
cp /opt/zero2dash/.env.example /opt/zero2dash/.env
chmod 600 /opt/zero2dash/.env
```

### Pi-hole settings

Set at minimum:

- `PIHOLE_HOST`
- `PIHOLE_SCHEME` if `PIHOLE_HOST` is remote and does not already include `http://` or `https://`
- `PIHOLE_PASSWORD` for v6 session auth, or `PIHOLE_API_TOKEN` for legacy token auth
- `PIHOLE_VERIFY_TLS=false` for self-signed HTTPS, or `PIHOLE_CA_BUNDLE=/path/to/ca.pem` to trust a private CA
- `PIHOLE_TIMEOUT`
- `REFRESH_SECS`
- `FB_DEVICE` if you need to override `/dev/fb1`

Notes:

- `ACTIVE_HOURS` still applies to variants that support timed active windows, such as `piholestats_v1.2.py`.
- `piholestats_v1.3.py` is the always-on variant and does not use the sleeping screen logic.

### Google OAuth notes

- Use Desktop OAuth clients for Calendar and Photos.
- Loopback OAuth only: complete sign-in on the same machine as the script, or tunnel the callback port from a headless Pi with `ssh -L 8080:localhost:8080 pihole@pihole`.
- If the Google consent screen is in testing, add your account as a test user.
- `calendash-api.py` defaults `GOOGLE_TOKEN_PATH` to `token.json` relative to `/opt/zero2dash` under systemd.
- `photos-shuffle.py` uses `GOOGLE_TOKEN_PATH_PHOTOS` for its own token path.

## Drive-backed photos

`scripts/photos-shuffle.py` now treats `LOCAL_PHOTOS_DIR` as the primary source.

In the supported Drive-backed setup:

- Treat `LOCAL_PHOTOS_DIR` as Drive-owned content rather than a mixed manual folder.
- Use `scripts/drive-sync.py` to populate that directory from a shared Google Drive folder.
- `scripts/photo-resize.py` proportionally reduces new or changed images to 50% before they are reused locally.
- Normal personal or shared Google Photos albums are no longer a reliable headless source.
- If you still configure `GOOGLE_PHOTOS_ALBUM_ID`, treat it as an app-created-album fallback only.

Required configuration:

- `LOCAL_PHOTOS_DIR`
- `GOOGLE_DRIVE_FOLDER_ID`
- `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` (`~/.config/zero2dash/drive-service-account.json` is the recommended Pi path)

Recommended workflow:

```sh
python3 scripts/drive-sync.py --list-remote --debug
python3 scripts/drive-sync.py --debug
python3 scripts/photos-shuffle.py --test --debug
```

When `GOOGLE_DRIVE_FOLDER_ID` is configured, `photos-shuffle.py` restricts local selection to files tracked in `GOOGLE_DRIVE_SYNC_STATE_PATH` instead of sampling unrelated files from the directory.

## Run via systemd

Install and enable the canonical units:

```sh
sudo cp /opt/zero2dash/systemd/*.service /etc/systemd/system/
sudo cp /opt/zero2dash/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now display.service
sudo systemctl enable --now day.timer night.timer
```

## Useful checks

```sh
journalctl -u display.service -n 50 --no-pager
journalctl -u pihole-display-dark.service -n 50 --no-pager
python3 scripts/piholestats_v1.2.py --check-config
python3 scripts/piholestats_v1.2.py --diagnose-api
python3 scripts/piholestats_v1.3.py --check-config
python3 scripts/photos-shuffle.py --check-config
```

## Notes

- `display_rotator.py` excludes `piholestats_v1.2.py`, `calendash-api.py`, `_config.py`, `drive-sync.py`, and `photo-resize.py` by default so helper scripts do not end up in the day rotator.
- `calendash-img.py` is a rotator-friendly page script, not a systemd service unit on its own.
- Both canonical service units set `FB_DEVICE=/dev/fb1` by default and then load `/opt/zero2dash/.env`, so `.env` can still override the framebuffer device without editing the unit files.
