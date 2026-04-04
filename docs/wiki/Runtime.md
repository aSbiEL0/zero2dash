# Runtime

## Shell

`boot/boot_selector.py` owns:

- theme discovery from `themes/*`
- menu and screen routing
- shell-owned placeholder flows
- request-file mode switching
- child lifecycle ownership

## Child Apps

- `display_rotator.py` remains the Dashboards child entrypoint
- `modules/photos/slideshow.py` remains the Photos child entrypoint
- `modules/blackout/blackout.py` remains the Night compatibility path
- `player.py` is the foreground credits/vault video player child

## Touch and Return

- `rotator/touch.py` emits `MAIN_MENU` on long press
- The shell reclaims control only after child shutdown
- `menu` requests return to the last root page for the current session
- The shell strip/back action now uses the rightmost `20px` on stripe-based screens
- ADS7846 touch selection accepts `ABS_X`/`ABS_Y` plus `EV_SYN` fallback samples when explicit touch-state events are absent

## Assets

- `mainmenu1.png` and `mainmenu2.png` are the root screens
- `day-night.png`, `settings.png`, `themes.png`, `yes-no.png`, `keypad.png`, and `stats.png` drive child screens and placeholders
- `player.png` and `overlay.png` are required per-theme player assets
- `themes/global_images/vault.png` is the fixed vault-mode background override
- `credits.gif` remains on disk in `boot/`, but the normal Credits button flow no longer uses it
- Verified installed theme directories are `carbon`, `comic`, `frosty`, and `steele`
- `yes-no.png` maps `tick` to confirm and `red X` to cancel
- `keypad.png` uses the real 4x3 layout, and only consecutive failed keypad submissions count toward shutdown

## Player Flow

- Credits launch the foreground player against `~/vid`
- Correct PIN entry launches the same player against `~/x`
- The player owns touch while running and exits back to the shell on its own back-strip / hold gestures

## Settings Layout

- Settings/status screens are rendered by `draw_status_screen()` in `boot/boot_selector.py`
- The operator-tunable layout values now live near the top of `boot/boot_selector.py`
- Title and body text each expose `x`, `y`, width, height, font path, and font size controls
- Line spacing and bottom margin are also exposed in code
