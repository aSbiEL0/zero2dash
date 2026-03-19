# Project Status

Last updated: 2026-03-19

Live status: ACTIVE

## Active Execution State

- `PLAN.md` now points at the active shell-owned app stabilization plan.
- Current remediation scope is Photos, Settings, Themes, and dashboard-layout guidance.
- Dashboard is not in a rebuild stream; only minor layout tuning is in scope there.
- Shell-first runtime remains accepted:
  - `boot/boot_selector.py` is the parent shell
  - `display_rotator.py` is the dashboards child entrypoint
  - `modules/photos/slideshow.py` is the Photos child entrypoint

## Active Workstreams

- `R-015` Mouser: planning reset and live coordination reopen. COMPLETE.
- `R-016` Pathfinder: verify theme/assets and Photos touch seams. OPEN.
- `R-017` Photos Worker: add dashboard-style touch behavior to Photos. OPEN.
- `R-018` Switchboard: implement Settings summaries, generated Themes picker, and shell layout knobs. OPEN.
- `R-019` Sentinel: add regression coverage for Photos, Settings, and Themes. OPEN.
- `R-020` Curator: update operator-facing docs after stabilization. OPEN.

## Sequencing

1. `R-015` coordination reset
2. `R-016` verified contract scan
3. `R-017` Photos stream and `R-018` Switchboard stream in parallel
4. `R-019` regression hardening
5. Mouser integration verification
6. `R-020` documentation pass

## Current Repo Reality

- The previous shell-repair slice is complete and archived.
- Remaining functional work is concentrated in Photos, Settings, and Themes.
- The operator confirmed the Dashboard app only needs minor layout/margin tuning.
- The operator requested Photos to behave like Dashboard touch navigation:
  - left tap previous
  - right tap next
  - hold exit
- The operator requested Settings to show operator-summary content.
- The operator clarified Themes should support a generated touch/path mapping and there will not be more than 6 themes active.

## Validation Target

- Hardware-free pass for:
  - `tests/test_boot_selector.py`
  - `tests/test_photos.py`
  - `tests/test_display_rotator.py`
- compile/import sanity for:
  - `boot/boot_selector.py`
  - `modules/photos/slideshow.py`
  - `modules/photos/display.py`

## Open Notes

- No active technical blocker is recorded yet.
- The next decisive fact-gathering step is the Pathfinder verification pass before implementation begins.
