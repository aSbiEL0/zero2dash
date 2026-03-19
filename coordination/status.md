# Project Status

Last updated: 2026-03-19

Live status: ACTIVE

## Active Execution State

- `PLAN.md` now points at the post-merge shell stabilization slice.
- The active goal is shell/menu cleanup after the bad NASA-branch merge.
- NASA app work is explicitly out of scope for this slice.
- Shell-first runtime remains accepted:
  - `boot/boot_selector.py` is the parent shell
  - `display_rotator.py` remains the Dashboards child entrypoint
  - `modules/photos/slideshow.py` remains the Photos child entrypoint

## Active Workstreams

- `R-021` Mouser: control-plane reset and agent alignment. COMPLETE.
- `R-022` Pathfinder: verify Themes/touch/Settings reality. OPEN.
- `R-023` Switchboard: fix Themes order and lower-row inactivity. OPEN.
- `R-024` Switchboard: reformat Settings rendering only. OPEN.
- `R-025` Sentinel: regression hardening. OPEN.
- `R-026` Curator: finalize docs after behavior stabilizes. OPEN.
- `R-027` Framekeeper: reserve-only escalation path. HOLD.

## Sequencing

1. `R-021` control-plane reset
2. `R-022` repo-reality verification
3. `R-023` Themes fix
4. `R-024` Settings formatting
5. `R-025` regression hardening
6. Mouser integration verification and reserve-role decision
7. `R-026` documentation pass

## Current Repo Reality

- The previous shell-owned-app stabilization plan is now stale for the operator’s current goal.
- The current shell code still sorts theme ids and does not encode the visible art order the operator expects.
- The operator reported:
  - Themes top-row buttons are permuted against the art
  - hidden lower-row theme zones remain active
  - menu touch issues are menu-only as observed so far
  - Settings content is acceptable, but the current text drawing is unreadable
- Touch stabilization for this slice is calibration-first, not code-first.
- A future visual calibration UI is explicitly deferred.

## Validation Target

- Code-side:
  - `python -m unittest tests.test_boot_selector`
  - `python -m py_compile boot/boot_selector.py`
- On device:
  - `python3 boot/boot_selector.py --probe-touch`
  - `python3 boot/boot_selector.py --calibrate-touch`
  - apply printed `TOUCH_*` values
  - recheck visible shell zones on `main_menu_1`, `main_menu_2`, `settings`, and `themes`

## Open Notes

- No active blocker is recorded for this slice yet.
- Framekeeper remains reserve-only unless recalibrated shell menus still miss intended zones.
- Calendash remains operator-tunable but out of this implementation slice.
