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
- `R-016` Pathfinder: verify theme/assets and Photos touch seams. COMPLETE.
- `R-017` Photos Worker: add dashboard-style touch behavior to Photos. COMPLETE.
- `R-018` Switchboard: implement the shell-side Photos handoff, Settings summaries, generated Themes picker, and shell layout knobs. COMPLETE.
- `R-019` Sentinel: add regression coverage for Photos, Settings, and Themes. OPEN.
- `R-020` Curator: update operator-facing docs after stabilization. OPEN.

## Sequencing

1. `R-015` coordination reset
2. `R-016` verified contract scan
3. `R-017` Photos child stream and `R-018` Switchboard shell stream in parallel
4. `R-019` regression hardening
5. Mouser integration verification
6. `R-020` documentation pass

## Current Session Progress

- Mouser launched the `R-017` Photos child stream and `R-018` Switchboard shell stream in parallel.
- Coordination file edits remain centralized in Mouser to avoid merge churn while implementation proceeds in disjoint write sets.
- Photos child runtime now supports left/right navigation and hold-to-menu via the existing shell mode-request file contract.
- The shell no longer claims the Photos home gesture, Settings now renders fallback-safe operator summaries, and Themes now derives deterministic touch mapping from discovered theme ids capped at 6 items.
- Named shell status layout constants are now extracted in `boot/boot_selector.py`, and Pi Stats now includes uptime, load, temperature, memory, and disk summaries.

## Validation Snapshot

- `tests.test_boot_selector` passes under `C:\ISS\.venv\Scripts\python.exe`.
- `py_compile` passes for the touched shell and Photos files under LibreOffice Python with `C:\ISS\.venv\Lib\site-packages` on `PYTHONPATH`.
- `tests.test_photos` could not be executed locally because the available venv launcher points to an inaccessible base Python 3.13 interpreter, while LibreOffice Python 3.8 is too old for the installed Pillow build.
- `tests.test_display_rotator` currently fails `test_touch_worker_accepts_abs_syn_fallback_without_btn_touch` in unchanged rotator code during this environment's validation pass; this appears outside the edited file set and remains for follow-up confirmation.

## Current Repo Reality

- The previous shell-repair slice is complete and archived.
- Remaining functional work is concentrated in Photos, Settings, and Themes.
- The operator confirmed the Dashboard app only needs minor layout/margin tuning.
- Current installed valid themes are `comic`, `default`, and `steele`; `default` and `steele` also contain an extra unbound `1.png`.
- The operator requested Photos to behave like Dashboard touch navigation:
  - left tap previous
  - right tap next
  - hold exit
- The operator requested Settings to show operator-summary content.
- The operator clarified Themes should support a generated touch/path mapping and there will not be more than 6 themes active.
- Current code facts from the planning audit:
  - `boot/boot_selector.py` still hardcodes `THEME_PICKER_COLUMNS = ("default", "steele", "comic")`
  - `draw_status_screen()` still renders placeholder/env-driven status text only
  - `modules/photos/slideshow.py` is still timer-driven and has no touch input seam yet

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
- The implementation boundary is now explicit: `R-017` owns child-side Photos input, while `R-018` owns every `boot/boot_selector.py` change, including the Photos shell handoff.
