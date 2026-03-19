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

## Touch and Return

- `rotator/touch.py` emits `MAIN_MENU` on long press
- The shell reclaims control only after child shutdown
- `menu` requests return to the last root page for the current session

## Assets

- `mainmenu1.png` and `mainmenu2.png` are the root screens
- `day-night.png`, `settings.png`, `themes.png`, `yes-no.png`, `keypad.png`, and `stats.png` drive child screens and placeholders
- `credits.gif` and `startup.gif` remain shared boot assets
