# Project Status

Last updated: 2026-03-19

`PLAN.md` is the only execution source of truth. This file is a current-run status summary only.

## Current Execution State

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

## Active Workstreams

- `R-013` Curator: complete.
- `R-014` Mouser: in progress.
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
- Pi smoke testing is now in progress for touch hardware, framebuffer ownership, and real service interaction.
- Current Pi note: the shell now boots to the themed main menu on device.
- Latest repo note: the touch-remediation slice is now implemented locally. It adds reusable touch calibration, routes root Dashboards through `dashboards_menu`, closes the shell reader while Dashboard/Night own touch, and teaches shell/rotator/blackout to consume ADS7846 `ABS_X/ABS_Y + EV_SYN` gestures.
- Latest Pi runtime note: ADS7846 touch selection now reaches `dashboards_menu`, but Pi smoke exposed two child-app crashes instead of touch freezes:
  - `display_rotator.py` called its local `discover_pages()` wrapper with an unsupported `resolve_path=` keyword
  - `modules/blackout/blackout.py` failed to import `framebuffer` when launched as a child by path from the repo root
- Latest repo fix note: Mouser patched both child launch regressions and added a regression test for the rotator `parse_pages()` path.
- Latest Pi keypad note: Dashboard now runs on device, but the shell keypad still used the wrong logical layout. The actual `keypad.png` asset is a 4x3 grid (`1 2 3 tick` / `4 5 6 0` / `7 8 9 red X`), so the selector's old 3x4 phone-style hit map sent keypad taps to the wrong actions.
- Latest repo keypad fix note: Mouser updated the keypad resolver and selector tests to match the real asset contract so red X cancels and the green tick submits.
- Latest validation note: hardware-free Python test execution is still blocked in this shell by a local interpreter wrapper issue, so the next meaningful gate is Pi retest with the updated branch.
- Repo docs are updated, wiki-ready content is prepared under `docs/wiki/`, and remote publication is pending Pi smoke confirmation.

## Archive Note

- Older coordination entries from the previous agent team are historical only.
- If any archive text conflicts with `PLAN.md`, `PLAN.md` wins without exception.
