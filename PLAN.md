# Active Plan: Post-Merge Shell Stabilization

Status: ACTIVE  
Date: 2026-03-19

This plan supersedes the previous shell-owned-app stabilization slice.

The active execution plan is:

- `docs/plans/post-merge-shell-stabilization.md`

## Scope

- Fix post-merge shell/menu regressions without reopening NASA app work.
- Keep the accepted shell-first runtime:
  - `boot/boot_selector.py` remains the parent shell
  - `display_rotator.py` remains the Dashboards child entrypoint
  - `modules/photos/slideshow.py` remains the Photos child entrypoint
- Refresh planning, coordination, and agent instructions so the next execution pass starts from one clean source of truth.

## Current Intent

- Themes must match the visible art:
  - explicit order `default`, `steele`, `comic`
  - lower-row theme zones inactive until future visible buttons/assets exist
- Menu touch stabilization is calibration-first:
  - use `--probe-touch`
  - use `--calibrate-touch`
  - apply exported `TOUCH_*` values
  - do not change touch math unless recalibrated on-device checks still miss targets
- Settings stays in scope, but only as a formatting/rendering task:
  - keep current summary content
  - redraw title and body as a centered composition shifted 10px left
  - prefer fewer lines with truncation over dense wrapping
- Calendash implementation is out of scope for this slice.
  - Operator tuning seam remains `modules/calendash/calendash-api.py`

## Non-Goals

- No NASA app feature/debug work
- No Photos behavior changes
- No rotator rewrite
- No systemd/timer changes
- No new dependency introduction without approval
- No visual on-device calibration UI in this slice

## Execution Model

- Mouser owns sequencing, delegation, review gates, and coordination hygiene.
- Pathfinder performs the first read-only verification pass.
- Switchboard owns all shell/runtime implementation in `boot/boot_selector.py`.
- Sentinel owns regression coverage and acceptance checks.
- Curator lands the final docs and AGENTS refresh after behavior is stable.
- Framekeeper remains reserve-only and is spawned only if recalibrated menu touches still misfire and the blocker is no longer explainable by shell mapping or stale calibration.
