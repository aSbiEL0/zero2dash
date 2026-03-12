# Raspberry Pi update guide (zero2dash)

This guide walks you through safely updating a Pi that already runs `zero2dash`, then checking whether your `.env` file needs changes.

## 1) SSH to the Pi and create a rollback backup

```bash
ssh pi@<pi-ip>
sudo systemctl stop display.service pihole-display-dark.service currency-update.service day.timer night.timer currency-update.timer
sudo mkdir -p /opt/backups
sudo tar -czf /opt/backups/zero2dash-$(date +%F-%H%M).tgz /opt/zero2dash
```

## 2) Update the code in `/opt/zero2dash`

If your deployment is a git checkout:

```bash
cd /opt/zero2dash
git fetch --all --prune
git status
git pull --ff-only
```

If your deployment is copied files instead of git, copy fresh files from your dev machine into `/opt/zero2dash`.

## 3) Ensure required runtime packages are present

```bash
sudo apt update
sudo apt install -y python3-pip python3-pil
```

## 4) Refresh systemd units from the repo

```bash
sudo cp /opt/zero2dash/systemd/*.service /etc/systemd/system/
sudo cp /opt/zero2dash/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

## 5) Check whether `.env` needs amending

Your active config should be `/opt/zero2dash/.env` because both canonical services load this file.

### 5a) Confirm the file exists and is secured

```bash
sudo test -f /opt/zero2dash/.env && echo ".env exists"
sudo chmod 600 /opt/zero2dash/.env
```

If missing:

```bash
sudo cp /opt/zero2dash/.env.example /opt/zero2dash/.env
sudo chmod 600 /opt/zero2dash/.env
```

### 5b) Diff your current `.env` against the latest `.env.example`

```bash
cd /opt/zero2dash
comm -23 \
  <(grep -E '^[A-Z0-9_]+=' .env.example | cut -d= -f1 | sort -u) \
  <(grep -E '^[A-Z0-9_]+=' .env | cut -d= -f1 | sort -u)
```

If this prints keys, they are new keys present in `.env.example` but missing from your `.env`; add them.

### 5c) Minimum values to verify for a healthy deploy

At minimum, check these are set correctly for your environment:

- `PIHOLE_HOST`
- `PIHOLE_PASSWORD`
- `PIHOLE_API_TOKEN` (optional fallback)
- `REFRESH_SECS`
- `ACTIVE_HOURS`
- `FB_DEVICE` (optional; defaults to `/dev/fb1`)
- `FB_WIDTH` and `FB_HEIGHT` (optional; defaults are `320` and `240` where used)

If you use Google-backed pages, also verify:

- Calendar: `GOOGLE_CALENDAR_CLIENT_ID` + `GOOGLE_CALENDAR_CLIENT_SECRET` (or shared Google creds), `GOOGLE_CALENDAR_ID`, `TIMEZONE`
- Photos: `GOOGLE_PHOTOS_ALBUM_ID` and either `GOOGLE_PHOTOS_CLIENT_SECRETS_PATH` or `GOOGLE_PHOTOS_CLIENT_ID` + `GOOGLE_PHOTOS_CLIENT_SECRET`

### 5d) Validate Google Photos auth wiring (optional but recommended)

```bash
cd /opt/zero2dash
python3 scripts/photos-shuffle.py --check-config
```

This shows which credential source is being used and whether config is complete.

## 6) Re-enable and start services

```bash
sudo systemctl enable --now display.service
sudo systemctl enable --now day.timer night.timer currency-update.timer
```

If you want to immediately test night mode too:

```bash
sudo systemctl start pihole-display-dark.service
```

The night service now runs `/opt/zero2dash/scripts/blackout.py`, which expects `/opt/zero2dash/images/raspberry-pi-icon.png` to be present in the deployed tree.

## 7) Post-update verification

```bash
systemctl status display.service --no-pager
systemctl status pihole-display-dark.service --no-pager
systemctl status currency-update.service --no-pager
systemctl list-timers --all | grep -E 'day.timer|night.timer|currency-update.timer'
journalctl -u display.service -n 50 --no-pager
journalctl -u pihole-display-dark.service -n 50 --no-pager
journalctl -u currency-update.service -n 50 --no-pager
```

## 8) Quick rollback (if needed)

```bash
sudo systemctl stop display.service pihole-display-dark.service currency-update.service
sudo rm -rf /opt/zero2dash
sudo tar -xzf /opt/backups/<backup-file>.tgz -C /
sudo systemctl daemon-reload
sudo systemctl start display.service
```

## Notes about the IDE `.env` path in your context

Your IDE referenced a Windows path (`C:/Users/Default.DESKTOP-MR88P09/.env`). For the Pi runtime, the file that matters is `/opt/zero2dash/.env` because that is what the systemd units load.




