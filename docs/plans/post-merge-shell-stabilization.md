# Post-Merge Shell Stabilization

Goal: restore clean, reliable shell/menu behavior after the bad NASA-branch merge without reopening NASA app work.

## Scope

- Themes screen order and touch mapping
- Inactive lower-row theme zones
- Menu-touch recalibration workflow and sign-off
- Settings text rendering only
- Planning/coordination/agent alignment

## Out of Scope

- NASA app behavior
- Photos behavior
- Rotator feature work
- Systemd changes
- Visual calibration UI

## Team

- Mouser: orchestration, review gates, coordination
- Pathfinder: read-only repo reality scan
- Switchboard: shell/menu/runtime changes
- Sentinel: regression protection
- Curator: final docs and AGENTS sync
- Framekeeper: reserve only if touch issues remain after recalibration

## Ordered Work

1. Mouser replaces stale planning and coordination state.
2. Pathfinder verifies current shell/theme/touch reality against repo assets and tests.
3. Switchboard fixes the Themes screen:
   - visible order is `default`, `steele`, `comic`
   - lower row is inactive
4. Switchboard reformats Settings rendering only:
   - keep existing status providers
   - center title/body as one composition
   - shift composition 10px left
   - increase spacing
   - prefer truncation/ellipsis over dense wrapping
5. Sentinel updates selector regressions and sign-off checks.
6. Mouser runs integration checks and decides whether Framekeeper is needed.
7. Curator finalizes README, AGENTS, and coordination close-out.

## Validation

- `python -m unittest tests.test_boot_selector`
- `python -m py_compile boot/boot_selector.py`
- On device:
  - `python3 boot/boot_selector.py --probe-touch`
  - `python3 boot/boot_selector.py --calibrate-touch`
  - apply printed `TOUCH_*` values
  - recheck visible shell zones on `main_menu_1`, `main_menu_2`, `settings`, and `themes`

## Acceptance Criteria

- Themes top-row buttons trigger the theme shown by the art.
- Themes lower-row zones do nothing.
- Shell menus hit the intended zones after documented recalibration.
- Settings text becomes readable without changing underlying summary content.
- Planning, AGENTS, and coordination files all point to this slice and no older slice remains active.
