# zero2dash

Framebuffer dashboard stack for a 320x240 SPI TFT on Raspberry Pi.

- Direct rendering to `/dev/fb1`
- No X11, Wayland, SDL, or browser runtime
- `PLAN.md` is the active source of truth for the current shell rebuild

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

## Rebuild Status

- `boot/boot_selector.py` is now the themed shell runtime
- `display_rotator.py` remains the Dashboards child entrypoint
- `modules/photos/slideshow.py` remains the Photos child entrypoint
- The shell uses real assets from `themes/default`, `themes/comic`, and `themes/steele`
- Theme selection is persisted only; root-page return state is session-only
- `rotator/touch.py` restores long-press `MAIN_MENU` return behavior
- Hardware-free tests cover the repaired rotator path and the rebuilt selector/router

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
| Rotator slice | `python3 -m unittest tests.test_display_rotator` | Covers the extracted touch and screen-power paths. |
| Selector/router slice | `python3 -m unittest tests.test_boot_selector` | Covers themed routing, theme discovery, and mode handling. |
| Framebuffer slice | `python3 -m unittest tests.test_framebuffer` | Covers RGB565 conversion and framebuffer writes. |
| Tram render | `python3 modules/trams/display.py --self-test` | Checks a representative image-producing module. |

## Remaining Risks

- Pi-side validation is still required for touch hardware, framebuffer ownership, and service interaction.
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
