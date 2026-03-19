# Project Status

Last updated: 2026-03-19

Archive status: CLOSED on 2026-03-19.

This file is now an archive summary for the completed shell-repair run.
It is not the live status board for the next planning cycle.

## Archived Execution State

- The active execution plan is `PLAN.md`.
- `boot/boot_selector.py` remains the parent shell.
- `display_rotator.py` remains the dashboards child entrypoint.
- `modules/photos/slideshow.py` remains the Photos child entrypoint.
- Shell modes remain `menu`, `dashboards`, `photos`, and `night`.

## Current Repo Reality

- The selector runtime now uses the theme-backed screen model from `PLAN.md`.
- Real theme assets exist under `themes/default`, `themes/comic`, and `themes/steele`.
- Shared non-theme boot assets remain `boot/startup.gif` and `boot/credits.gif`.
- The rotator/dashboard conflict residue has been removed from `display_rotator.py`, `display_layout.py`, and `modules/trams/display.py`.
- `rotator/touch.py` again emits `MAIN_MENU` on long press.
- `boot/boot_selector.py` now discovers themes from `themes/*`, persists only the selected theme, and routes through explicit screen states instead of the old paged tile UI.

## Archived Workstreams

- `R-013` Curator: complete.
- `R-014` Mouser: complete.
- `R-009` Mouser: coordination reset, dependency tracking, merge control.
- `R-010` Rotor: complete.
- `R-011` Switchboard: complete.
- `R-012` Sentinel: complete.

## Merge Order

1. `R-009` coordination sync
2. `R-010` rotator/dashboard repair
3. `R-011` shell rewrite
4. `R-012` regression coverage
5. Mouser integration pass

## Validation Status

- Rotator import/runtime validation passed after merge-conflict cleanup and long-press restoration.
- Boot selector smoke checks passed for `py_compile` and `--dump-contracts --skip-gif --no-framebuffer`.
- Hardware-free selector and rotator regression suites now pass.
- The Pi shell baseline is now usable and the remaining work has moved to app-specific debugging.
- Current Pi note: the shell now boots to the themed main menu on device and the real keypad contract is working.
- Latest repo note: the touch-remediation slice is now implemented locally. It adds reusable touch calibration, routes root Dashboards through `dashboards_menu`, closes the shell reader while Dashboard/Night own touch, and teaches shell/rotator/blackout to consume ADS7846 `ABS_X/ABS_Y + EV_SYN` gestures.
- Latest repo note: the child launch regressions and keypad/PIN-state issues have been fixed, including the real 4x3 `keypad.png` layout and the consecutive-failure shutdown rule.
- Repo docs are updated and the shell validation handoff is complete; remaining validation belongs to app-specific streams.

## Archive Note

- Older coordination entries from the previous agent team are historical only.
- This completed run is historical as well. A new plan should establish the next live status source.
