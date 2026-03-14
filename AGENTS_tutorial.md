zero2dash — tutorial walkthrough for agents
Goal
Bring up zero2dash on a Raspberry Pi with a 320×240 SPI TFT using framebuffer rendering and systemd. This document assumes you are working in the repository root.
Step A — Understand the moving parts
    1. Day mode rotates pages:
    2. display_rotator.py discovers modules and launches modules/<name>/display.py.
    3. Night mode runs a blackout/animation:
    4. modules/blackout/blackout.py.
    5. systemd glues everything together:
    6. systemd/display.service (day)
    7. systemd/night.service (night)
    8. systemd/day.timer and systemd/night.timer (schedule)
    9. systemd/currency-update.timer (background refresh)
Step B — Safe local validation (no Pi hardware required)
Run:
python3 -m pip install -r requirements.txt
python3 display_rotator.py --list-pages
python3 display_rotator.py --probe-touch
For page scripts, prefer “no framebuffer” outputs:
python3 modules/calendash/display.py --output /tmp/calendash.png --no-framebuffer
python3 modules/trams/display.py --output /tmp/trams.png --no-framebuffer
Step C — Configure runtime environment (Pi)
    1. Create .env from the template and lock its permissions:
cp .env.example .env
chmod 600 .env
    1. Fill in only what you need:
    2. Pi‑hole: set PIHOLE_HOST, plus either PIHOLE_PASSWORD or PIHOLE_API_TOKEN.
    3. Calendar: set GOOGLE_* variables and TIMEZONE.
    4. Photos: set LOCAL_PHOTOS_DIR if using a local directory. The Google Photos API is optional.
    5. Trams/currency: optional; defaults exist.
Step D — Running under systemd (ask before changing system files)
Before proposing any sudo cp systemd/*.service … or systemctl enable …, confirm:
    • The correct repository checkout path (units assume /home/pihole/zero2dash).
    • The desired day/night times (timers are currently set to 07:00 and 22:00).
If explicitly approved:
    1. Ensure pihole-display-pre.sh is executable.
    2. Reload the daemon and enable timers/services.
    3. Verify via systemctl status … and journalctl -u ….
Step E — Adding a new page module (high‑level)
A new module should be:
    • A new folder under modules/<newmodule>/.
    • Must include display.py as the entrypoint (or adjust ROTATOR_MODULE_ENTRYPOINT).
    • Should support at least one of:
    • --no-framebuffer + --output
    • --check-config
    • --self-test
Then update modules.txt to include the module name in the desired order.
Troubleshooting checklist
    • Rotation shows blank or old image: the page may exit early; run the page script directly with safe flags.
    • Touch not working: use python3 display_rotator.py --probe-touch; set TOUCH_DEVICE if needed.
    • Service loops: check journal output and page exit codes; rotator backoff and quarantine is expected behaviour.
