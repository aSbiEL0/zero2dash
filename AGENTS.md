zero2dash — AGENTS.md (repository‑specific guidance)
Overview
zero2dash is a Raspberry Pi dashboard that renders directly to the Linux framebuffer (/dev/fb1) at 320×240. It intentionally avoids graphical desktops (X11/Wayland/SDL) and instead runs page scripts as subprocesses. The runtime is orchestrated by Python scripts and systemd units. Day mode rotates "page scripts" found under modules/<module>/display.py. Night mode runs a blackout animation.
Non‑negotiables (Do / Don’t)
Do
    • Prefer minimal, targeted diffs; keep behaviour stable.
    • Follow existing patterns: use argparse CLIs and implement flags such as --check-config, --self-test, and --no-framebuffer or --output where applicable.
    • Preserve the module contract: each module must provide modules/<name>/display.py unless the rotator entry point is explicitly changed.
    • Use _config.get_env() and report_validation_errors() to validate new environment variables in modules that already use that pattern.
    • Keep secrets out of version control: .env, token*.json, API keys and Pi‑hole passwords must never be committed.
    • When adding configuration variables, also update .env.example and README.md.
Don’t
    • Don’t “modernise” the project by adding a GUI stack (X11/Wayland/browser) unless explicitly asked.
    • Don’t add new dependencies without approval.
    • Don’t refactor multiple files (especially display_rotator.py) unless requested; reliability is prioritised over architectural purity.
    • Don’t touch /etc/systemd/system, use sudo, change device permissions/groups, or alter timer schedules without explicit approval.
Project map (start here)
    • Rotator logic: display_rotator.py — rotates pages and handles touch controls.
    • Shared environment helpers: _config.py — exposes get_env() and report_validation_errors().
    • Module order: modules.txt — determines rotation order; if absent, modules are scanned alphabetically.
    • Runtime configuration template: .env.example — copy to .env and populate secrets; keep file permissions restrictive.
    • Services and timers: systemd/ — contains systemd service and timer units.
    • Boot selector: boot/boot_selector.py — selects day/night mode at boot.
    • Page modules: modules/<module>/display.py — entry point for each module.
How page discovery works (important)
display_rotator.py reads modules from the directory specified by ROTATOR_MODULES_DIR (default modules/). If the file specified by ROTATOR_MODULE_ORDER_FILE (default modules.txt) exists, it determines the page order; otherwise modules are discovered alphabetically. Each module must contain a file named by ROTATOR_MODULE_ENTRYPOINT (default display.py). A manual override is provided by ROTATOR_PAGES, a comma‑separated list of scripts.
Relevant environment variables:
    • ROTATOR_MODULES_DIR (default modules)
    • ROTATOR_MODULE_ORDER_FILE (default modules.txt)
    • ROTATOR_MODULE_ENTRYPOINT (default display.py)
    • ROTATOR_PAGES (manual override; comma‑separated)
    • ROTATOR_FBDEV (framebuffer device; default /dev/fb1)
    • TOUCH_DEVICE / ROTATOR_TOUCH_DEVICE (force specific input device)
    • ROTATOR_SECS (rotation interval, clamped to at least 5 seconds)
    • ROTATOR_BACKOFF_MAX_SECS, ROTATOR_QUARANTINE_FAILURE_THRESHOLD, ROTATOR_QUARANTINE_CYCLES (resilience controls)
When editing module discovery logic, ensure that the output of python3 display_rotator.py --list-pages stays accurate and informative.
Configuration conventions
    • .env is loaded by several scripts via python‑dotenv. It must never be committed. Duplicate secrets (tokens, passwords) should be stored locally only.
    • When adding a new environment variable:
    • Implement validation using _config.get_env() and update error messages.
    • Update .env.example with the new variable and defaults.
    • Update README.md (Configuration section).
    • Provide any migration steps or default values.
    • Common tokens/credentials:
    • Calendar: token.json relative to the working directory.
    • Photos: token_photos.json (see the photos module).
    • Pi‑hole: PIHOLE_HOST and PIHOLE_PASSWORD or PIHOLE_API_TOKEN.
    • Framebuffer and touch devices are hardware‑specific:
    • Framebuffer: typically /dev/fb1.
    • Touch: automatically selected from /dev/input/event* but can be forced via environment variables.
Safe commands (prefer these)
Install dependencies
python3 -m pip install -r requirements.txt
Discovery / diagnostics
# Show which pages exist and why
python3 display_rotator.py --list-pages
# Touch selection and calibration hints
python3 display_rotator.py --probe-touch
Configuration checks (safe; avoid framebuffer)
python3 modules/calendash/calendash-api.py --check-config
python3 modules/photos/display.py --check-config
python3 modules/photos/drive-sync.py --check-config
python3 modules/photos/photo-resize.py --check-config
python3 modules/currency/currency-rate.py --check-config
python3 modules/pihole/display.py --check-config
python3 modules/trams/tram_gtfs_refresh.py --check-config
Local / dry-run output checks
python3 modules/currency/currency.py --self-test
python3 modules/currency/currency-rate.py --self-test
python3 modules/photos/display.py --test
python3 modules/calendash/display.py --output /tmp/calendash.png --no-framebuffer
python3 modules/pihole/display.py --output-image /tmp/pihole.png
python3 modules/trams/display.py --output /tmp/trams.png --no-framebuffer
Troubleshooting playbook
    • “No pages found”: run python3 display_rotator.py --list-pages and ensure modules.txt matches existing module directories.
    • “Touch disabled”: run python3 display_rotator.py --probe-touch; set TOUCH_DEVICE=/dev/input/eventX if needed.
    • “Framebuffer not found”: verify the correct device (default /dev/fb1) and ensure systemd services set FB_DEVICE / ROTATOR_FBDEV consistently.
    • “A page keeps failing”: the rotator uses backoff and quarantine; run the module script directly with its safe flags first.
Security and safety
    • Never print or paste secrets into pull requests or logs.
    • Treat systemd units and device access as high‑risk changes: always ask for explicit approval before modifying services, timers, or device permissions.
    • Propose hardening (e.g. running under a non‑root user, systemd sandboxing) only when requested and include clear rollback steps.
Contribution expectations
    • Keep commits logically scoped and minimal.
    • When you change behaviour, update README.md and .env.example accordingly.
    • Prefer adding or updating lightweight self‑tests (e.g., --self-test) when editing non‑trivial logic.
    • Update modules.txt when adding, removing, or reordering modules.
When ambiguous
If unsure about hardware paths (e.g., /dev/fb*, /dev/input/event*), day/night schedules, or secrets/token locations, ask a clarifying question rather than guessing.
