# Raspberry Pi update guide (zero2dash)

This guide updates an existing Pi deployment and validates the current module-based layout.

## 1) Connect and take a rollback backup

```bash
ssh pi@<pi-ip>
cd /home/pihole/zero2dash
sudo systemctl stop display.service night.service currency-update.service day.timer night.timer currency-update.timer
mkdir -p backups
tar -czf backups/zero2dash-$(date +%F-%H%M).tgz .
```

## 2) Update the project files

If the Pi uses a git checkout:

```bash
git fetch --all --prune
git status
git pull --ff-only
```

If the Pi uses copied files, sync the updated project tree into the same directory.

## 3) Refresh Python dependencies

```bash
cd /home/pihole/zero2dash
python3 -m pip install -r requirements.txt
```

If needed:

```bash
sudo apt update
sudo apt install -y python3-pip python3-pil libjpeg-dev zlib1g-dev
```

## 4) Refresh systemd units

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

## 5) Check `.env`

The active runtime config file is `/home/pihole/zero2dash/.env`.

Ensure it exists and is secured:

```bash
test -f .env && echo ".env exists"
chmod 600 .env
```

If missing:

```bash
cp .env.example .env
chmod 600 .env
```

Compare the current file against `.env.example`:

```bash
comm -23 \
  <(grep -E '^[A-Z0-9_]+=' .env.example | cut -d= -f1 | sort -u) \
  <(grep -E '^[A-Z0-9_]+=' .env | cut -d= -f1 | sort -u)
```

## 6) Validate module configuration

```bash
python3 modules/calendash/calendash-api.py --check-config
python3 modules/photos/photos-shuffle.py --check-config
python3 modules/photos/drive-sync.py --check-config
python3 modules/photos/photo-resize.py --check-config
python3 modules/currency/currency-rate.py --check-config
python3 modules/pihole/piholestats_manual.py --check-config
```

If you use Google-backed pages, also verify:

- Calendar: `GOOGLE_CALENDAR_ID`, `TIMEZONE`, and OAuth client credentials
- Photos: `LOCAL_PHOTOS_DIR` or Google Photos credentials plus `GOOGLE_PHOTOS_ALBUM_ID`

## 7) Re-enable services and timers

```bash
sudo systemctl enable --now display.service
sudo systemctl enable --now day.timer night.timer currency-update.timer
```

Optional immediate checks:

```bash
sudo systemctl start night.service
sudo systemctl restart currency-update.service
```

## 8) Post-update verification

```bash
systemctl status display.service --no-pager
systemctl status night.service --no-pager
systemctl status currency-update.service --no-pager
systemctl list-timers --all | grep -E 'day.timer|night.timer|currency-update.timer'
journalctl -u display.service -n 50 --no-pager
journalctl -u night.service -n 50 --no-pager
journalctl -u currency-update.service -n 50 --no-pager
```

## 9) Functional spot checks

```bash
python3 modules/photos/photos-shuffle.py --test
python3 modules/currency/currency.py --self-test
python3 modules/pihole/piholestats_manual.py --output-image /tmp/pihole-test.png
python3 modules/calendash/display.py --output /tmp/calendash-display.png --no-framebuffer
```

## 10) Roll back if required

```bash
sudo systemctl stop display.service night.service currency-update.service
rm -rf /home/pihole/zero2dash/*
tar -xzf backups/<backup-file>.tgz -C /home/pihole/zero2dash
sudo systemctl daemon-reload
sudo systemctl start display.service
```
