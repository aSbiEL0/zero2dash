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
| `night.service` | `scripts/blackout.py` | **Night dark mode** (blackout animation) |
| `currency-update.service` | `scripts/currency-rate.py` | **06:00 currency image refresh** |
### Compatibility table (service → script → mode)

| Service | Script path | Mode / status |
| --- | --- | --- |
| `display.service` | `display_rotator.py` | Canonical day mode |
| `night.service` | `scripts/blackout.py` | Canonical night mode |
| `currency-update.service` | `scripts/currency-rate.py` | Daily GBP/PLN image refresh |
| `day-mode.service` | *(legacy alias; not shipped in this repo)* | Legacy naming; replace with `display.service` |
| `dark-mode.service` | *(legacy alias; not shipped in this repo)* | Legacy naming; replace with `night.service` |
## Repository layout

```text
zero2dash/
├── display_rotator.py
├── modules.txt                  # explicit rotator order (optional but recommended)
├── modules/
│   ├── pihole/
│   │   └── display.py
│   ├── calendash/
│   │   └── display.py
│   ├── currency/
│   │   └── display.py
│   └── photos/
│       └── display.py
├── scripts/
│   ├── _config.py
│   ├── pihole_api.py
│   ├── pihole-display-pre.sh
│   ├── blackout.py              # canonical dark-mode service target
│   ├── piholestats_manual.py    # legacy implementation behind modules/pihole/display.py
│   ├── calendash-api.py
│   ├── calendash-img.py         # legacy implementation behind modules/calendash/display.py
│   ├── currency-rate.py
│   ├── currency.py              # legacy implementation behind modules/currency/display.py
│   ├── photos-shuffle.py        # legacy implementation behind modules/photos/display.py
│   ├── drive-sync.py
│   └── photo-resize.py
├── systemd/
│   ├── display.service
│   ├── night.service
│   ├── currency-update.service
│   ├── currency-update.timer
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
sudo chmod +x scripts/pihole-display-pre.sh
```

## Configuration

Create and secure an env file:

```sh
cp .env.example .env
chmod 600 .env
```

Set at minimum for Pi-hole:

- `PIHOLE_HOST`
- `PIHOLE_SCHEME` if `PIHOLE_HOST` is remote and does not already include `http://` or `https://`
- `PIHOLE_PASSWORD` for v6 session auth, or `PIHOLE_API_TOKEN` for legacy token auth
- `PIHOLE_VERIFY_TLS=false` for self-signed HTTPS, or `PIHOLE_CA_BUNDLE=/path/to/ca.pem` to verify a private CA
- `PIHOLE_TIMEOUT`
- `REFRESH_SECS`
- `ACTIVE_HOURS` (inclusive `start,end` hour window in 24h format; cross-midnight values like `22,7` are supported)
- `FB_DEVICE` (optional override; defaults to `/dev/fb1`)
- `FB_WIDTH` / `FB_HEIGHT` (optional override for static renderer geometry; defaults `320x240`)

Google OAuth notes:

- Use Desktop OAuth clients for Calendar and Photos.
- Loopback OAuth only: complete sign-in on the same machine as the script, or tunnel the callback port from a headless Pi with `ssh -L 8080:localhost:8080 pihole@pihole`.
- If the Google consent screen is in testing, add your account as a test user.
- `calendash-api.py` defaults `GOOGLE_TOKEN_PATH` to `token.json` relative to the project root under systemd; `photos-shuffle.py` must keep using a separate `GOOGLE_TOKEN_PATH_PHOTOS`.

Drive-backed photos notes:

- `scripts/photos-shuffle.py` now treats `LOCAL_PHOTOS_DIR` as the primary source.
- Use `scripts/drive-sync.py` to populate that directory from a shared Google Drive folder.
- `scripts/photo-resize.py` proportionally reduces changed images to 50% before they are reused locally.
- Normal personal/shared Google Photos albums are no longer a reliable headless source; if you still configure `GOOGLE_PHOTOS_ALBUM_ID`, treat it as an app-created-album fallback only.

## Module discovery

`display_rotator.py` now discovers rotator pages from `modules/`.

- Each module lives in `modules/<name>/`.
- Each rotator-visible module must expose `display.py`.
- Helper files in the same module folder are ignored unless a module entrypoint calls them.
- `modules.txt` in the repo root controls module order when present.
- If `modules.txt` is absent, the rotator falls back to alphabetical discovery of `modules/*/display.py`.
- `ROTATOR_PAGES` still works as a manual override for backward compatibility.

Default rotator order file format:

```text
# one module directory name per line
pihole
calendash
currency
photos
```

Relevant discovery environment variables:

- `ROTATOR_MODULES_DIR` (default: `modules`)
- `ROTATOR_MODULE_ORDER_FILE` (default: `modules.txt`)
- `ROTATOR_MODULE_ENTRYPOINT` (default: `display.py`)


## Run via systemd
Install and enable canonical units:

```sh
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now display.service
sudo systemctl enable --now day.timer night.timer currency-update.timer
```

Useful checks:

```sh
journalctl -u display.service -n 50 --no-pager
journalctl -u night.service -n 50 --no-pager
journalctl -u currency-update.service -n 50 --no-pager
```


## Google Photos shuffle credential precedence

`scripts/photos-shuffle.py` resolves OAuth credentials in this order:

1. `GOOGLE_PHOTOS_CLIENT_SECRETS_PATH` file path from env/`.env` (default: `~/zero2dash/client_secret.json`)
2. `GOOGLE_PHOTOS_CLIENT_ID` + `GOOGLE_PHOTOS_CLIENT_SECRET` from env/`.env`
3. `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` from env/`.env` (legacy fallback)

Use `python3 scripts/photos-shuffle.py --check-config` to validate the configuration and print the credential source that will be used.

## Drive-backed photo sync

Use a shared Google Drive folder when you want remote photo management without depending on the now-hobbled Google Photos album API.

Required configuration:

- `LOCAL_PHOTOS_DIR`
- `GOOGLE_DRIVE_FOLDER_ID`
- `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` (`~/.config/zero2dash/drive-service-account.json` is the recommended Pi path)

Recommended workflow:

```sh
python3 scripts/drive-sync.py
python3 scripts/photos-shuffle.py --test
```

`drive-sync.py` downloads images from the shared Drive folder into `LOCAL_PHOTOS_DIR` and then runs `photo-resize.py`, which shrinks new or changed images to 50% of their original width and height before reuse.

## Notes

- `display_rotator.py` now discovers `modules/<name>/display.py` instead of scanning `scripts/*.py`.
- The current module entrypoints are compatibility wrappers over the existing script implementations, so the module layout is active without forcing a risky full code move in one pass.
- `scripts/blackout.py` expects the icon asset at `images/raspberry-pi-icon.png`.
- `currency-rate.py` remains the scheduled generator; `modules/currency/display.py` is the rotator-visible page entrypoint.

### Framebuffer overrides in systemd

Both canonical service units now set `FB_DEVICE=/dev/fb1` by default and load `.env` afterward, so setting `FB_DEVICE` in `.env` overrides the unit default without editing unit files.

