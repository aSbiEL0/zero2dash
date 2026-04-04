# zero2dash

Framebuffer dashboard stack for a 320x240 SPI TFT on Raspberry Pi.

- Direct rendering to `/dev/fb1`
- No X11, Wayland, SDL, or browser runtime
- `PLAN.md` is the active source of truth only when a task is open

## Runtime Overview

| Unit | Purpose | Entrypoint |
| --- | --- | --- |
| `boot-selector.service` | Primary shell runtime, themed menu/router, child-app lifecycle owner | `boot/boot_selector.py` |
| `display.service` | Manual compatibility wrapper for the Dashboards child | `display_rotator.py` |
| `night.service` | Manual/night compatibility wrapper | `modules/blackout/blackout.py` |
| `shell-mode-switch@.service` | Shell mode request bridge for timers and operators | `boot/boot_selector.py --request-mode <mode>` |
| `currency-update.service` | Independent refresh job for the GBP/PLN image | `modules/currency/currency-rate.py` |
| `weather.service` | Independent refresh job for the weather image | `modules/weather/weather_refresh.py` |
| `tram.service` | Independent refresh job for the cached Firswood tram timetable | `modules/trams/tram_gtfs_refresh.py` |
| `tram-alerts.service` | Independent refresh job for the cached Bee Network tram alerts | `modules/trams/tram_alerts_refresh.py` |

## Current Status

- `boot/boot_selector.py` is now the themed shell runtime
- `display_rotator.py` remains the Dashboards child entrypoint
- `modules/photos/slideshow.py` remains the Photos child entrypoint
- Verified installed theme ids are `carbon`, `comic`, `frosty`, and `steele`
- Theme selection is persisted only; root-page return state is session-only
- `rotator/touch.py` restores long-press `MAIN_MENU` return behavior
- The shell baseline is working on the Pi, including corrected Themes routing, a right-side back strip, and code-tunable Settings text layout
- Active task state belongs in `PLAN.md`

## Asset Contract

Theme assets live under `themes/`, one directory per theme.

Current theme IDs:

- `carbon`
- `comic`
- `frosty`
- `steele`

Each theme directory must provide:

- `mainmenu1.png`
- `mainmenu2.png`
- `day-night.png`
- `themes.png`
- `settings.png`
- `stats.png`
- `yes-no.png`
- `keypad.png`
- `granted.gif`
- `denied.gif`
- `player.png`
- `overlay.png`

`keypad.png` uses a 4x3 layout:

- `1 2 3 tick`
- `4 5 6 0`
- `7 8 9 red X`

Shared non-theme assets remain under `boot/`:

- `startup.gif`
- `credits.gif` (kept on disk but no longer used by the normal Credits button flow)

Player assets and flows:

- Credits now launch the Python framebuffer player against `~/vid`
- Vault success now launches the same player against `~/x`
- Normal player launches use the active theme `player.png` background plus `overlay.png`
- Vault mode overrides only the background image with `themes/global_images/vault.png`

## Shell Modes

- `menu`
- `dashboards`
- `photos`
- `night`

## Validation

| Scope | Command | Notes |
| --- | --- | --- |
| Shell contracts | `python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif` | Confirms the shell registry and mode surface. |
| Shell smoke | `python3 boot/boot_selector.py --no-framebuffer --skip-gif` | Verifies the shell boots without hardware writes. |
| Player self-test | `python3 player.py --self-test` | Checks playlist filtering, sort order, and wrap logic without framebuffer writes. |
| Player + shell slice | `python3 -m unittest discover -s tests -v` | Covers the new player logic and shell launch contract checks. |
| Touch probe | `python3 boot/boot_selector.py --probe-touch` | Prints the chosen touch device and probe reason. |
| Touch calibration | `python3 boot/boot_selector.py --calibrate-touch` | Captures four corner taps and prints suggested touch env values. |
| Tram render | `python3 modules/trams/display.py --self-test` | Checks a representative image-producing module. |

## Repo Map

```text
zero2dash/
├── PLAN.md
├── AGENTS.md
├── README.md
├── boot/
│   └── boot_selector.py
├── coordination/
├── docs/
│   └── wiki/
├── display_rotator.py
├── framebuffer.py
├── modules/
├── rotator/
├── systemd/
├── tests/
└── themes/
```

## Notes

- `modules/photos/slideshow.py` is the long-running Photos app.
- `display_rotator.py` is the supported Dashboards entrypoint.
- The shell’s menu contract is theme-backed, not the old paged tile UI.
- The shell strip/back action now lives on the rightmost `20px` for stripe-based screens.
- Credits and vault playback now route through the same Python framebuffer player instead of the old credits GIF / shell helper split.
- `pin_keypad` follows the real keypad asset: green tick submits, red X cancels, and only uninterrupted failed keypad submissions count toward shutdown.
- Settings/status text layout is code-tunable near the top of `boot/boot_selector.py` via explicit title/body position, size, font, and spacing constants.
- Touch calibration is env-driven. Use `TOUCH_SWAP_AXES`, `TOUCH_RAW_X_MIN`, `TOUCH_RAW_X_MAX`, `TOUCH_RAW_Y_MIN`, and `TOUCH_RAW_Y_MAX` after capturing values with `--calibrate-touch`.

