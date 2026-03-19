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
- Current Pi note: the original GIF/framebuffer crash is fixed locally and Pi testing has advanced to the next startup fault.
- Latest Pi note: a manual Pi run with `--skip-gif` exposed a second boot blocker, `PermissionError` while replacing `/tmp/zero2dash-shell-theme`; a follow-up hotfix now logs and continues instead of aborting shell startup when theme persistence fails.
- Repo docs are updated, wiki-ready content is prepared under `docs/wiki/`, and remote publication is pending Pi smoke confirmation.

## Archive Note

- Older coordination entries from the previous agent team are historical only.
- If any archive text conflicts with `PLAN.md`, `PLAN.md` wins without exception.
