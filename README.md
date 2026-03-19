# zero2dash

Framebuffer dashboard stack for a 320x240 SPI TFT on Raspberry Pi.

- Direct rendering to `/dev/fb1`
- No X11, Wayland, SDL, or browser runtime
- `PLAN.md` is the active source of truth for the current post-merge shell stabilization slice

## Active Focus

- Current scope is post-merge shell/menu stabilization.
- NASA app work is not part of the active slice.
- The current stabilization targets are:
  - Themes top-row order and lower-row inactivity
  - calibration-first menu touch sign-off
  - Settings text rendering only

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

## Runtime Status

- `boot/boot_selector.py` is now the themed shell runtime
- `display_rotator.py` remains the Dashboards child entrypoint
- `modules/photos/slideshow.py` remains the Photos child entrypoint
- The shell uses real assets from `themes/default`, `themes/comic`, and `themes/steele`
- Theme selection is persisted only; root-page return state is session-only
- `rotator/touch.py` restores long-press `MAIN_MENU` return behavior
- The shell baseline is usable on the Pi, including ADS7846 touch fallback handling, Dashboard/Night launch recovery, and keypad routing
- Hardware-free tests cover the repaired rotator path and the rebuilt selector/router
- Active clean-up work is focused on post-merge shell/menu regressions rather than new app work

## Asset Contract

Theme assets live under `themes/`, one directory per theme.

Current theme IDs:

- `default`
- `comic`
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

`keypad.png` uses a 4x3 layout:

- `1 2 3 tick`
- `4 5 6 0`
- `7 8 9 red X`

Shared non-theme assets remain under `boot/`:

- `startup.gif`
- `credits.gif`

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
| Touch probe | `python3 boot/boot_selector.py --probe-touch` | Prints the chosen touch device and probe reason. |
| Touch calibration | `python3 boot/boot_selector.py --calibrate-touch` | Captures four corner taps and prints suggested touch env values. |
| Rotator slice | `python3 -m unittest tests.test_display_rotator` | Covers the extracted touch and screen-power paths. |
| Selector/router slice | `python3 -m unittest tests.test_boot_selector` | Covers themed routing, theme discovery, and mode handling. |
| Framebuffer slice | `python3 -m unittest tests.test_framebuffer` | Covers RGB565 conversion and framebuffer writes. |
| Tram render | `python3 modules/trams/display.py --self-test` | Checks a representative image-producing module. |

## Remaining Risks

- Post-merge shell/menu cleanup still remains before the current slice is ready for execution.
- Menu touch sign-off still depends on documented on-device recalibration.
- `display.service` and `night.service` remain compatibility paths, not the primary runtime.

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
- `pin_keypad` follows the real keypad asset: green tick submits, red X cancels, and only uninterrupted failed keypad submissions count toward shutdown.
- Touch calibration is env-driven. Use `TOUCH_SWAP_AXES`, `TOUCH_RAW_X_MIN`, `TOUCH_RAW_X_MAX`, `TOUCH_RAW_Y_MIN`, and `TOUCH_RAW_Y_MAX` after capturing values with `--calibrate-touch`.
- The current Themes screen should behave as a visible top row only; lower-row theme zones are not part of the active contract.
