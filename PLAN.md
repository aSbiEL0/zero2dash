# Active Plan: Shell-Owned Apps, Themes, and Layout Stabilization

Status: ACTIVE  
Date: 2026-03-19

This file supersedes the archived shell-repair plan.

The active execution plan is:

- `docs/plans/shell-owned-apps-plan.md`

## Scope

- Fix the real remaining app/function issues in Photos, Settings, and Themes.
- Leave the Dashboard runtime alone except for minor layout tuning and documented margin controls.
- Preserve the accepted shell-first runtime:
  - `boot/boot_selector.py` remains the parent shell
  - `display_rotator.py` remains the dashboards child entrypoint
  - `modules/photos/slideshow.py` remains the Photos child entrypoint

## Current Intent

- Photos gains dashboard-parity touch behavior: left = previous, right = next, hold = exit.
- Settings stops using placeholder-only status screens and shows operator-summary content.
- Themes stops assuming exactly three hardcoded themes and becomes a generated picker that supports up to six installed themes on one screen.
- Dashboard layout changes remain narrow and optional:
  - global layout knobs live in `display_layout.py`
  - shell status text layout lives in `boot/boot_selector.py`
  - script-local offsets remain in the individual module files that already define them

## Non-Goals

- No rotator rewrite
- No systemd/timer changes
- No shared framebuffer refactor
- No new dependency introduction without approval

## Execution Model

- Mouser owns sequencing, delegation, coordination hygiene, and merge order.
- Switchboard owns shell changes in `boot/boot_selector.py`.
- Sentinel owns regression coverage.
- Pathfinder stays read-only and verifies asset/path contracts.
- A narrow Photos worker may be assigned to `modules/photos/*` by Mouser because no standing role currently owns that slice.
- Curator follows after behavior is stable.
