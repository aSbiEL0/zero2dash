# Project Status

Last updated: 2026-03-28

Live status: ACTIVE

## Active Execution State

- The active slice is Themes finalization, right-side back stripe behavior, and Settings layout stabilization.
- NASA app work is deferred until this slice is complete.
- Photos is out of active implementation scope for this slice.
- Shell-first runtime remains accepted:
  - `boot/boot_selector.py` is the parent shell
  - `display_rotator.py` is the dashboards child entrypoint
  - `modules/photos/slideshow.py` is the Photos child entrypoint

## Device Snapshot

- Host checked: `pihole`
- Repo path: `/home/pihole/zero2dash`
- Branch: `main`
- Commit: `f7f2a71`
- Repo status: clean
- Uptime at check: 5 days
- Confirmed running service from quick scan: `pihole-FTL.service`

## Verified Code Reality

- Device and local `boot/boot_selector.py` match in the key sections inspected for Themes routing, strip routing, and Settings status rendering.
- The device `boot/boot_selector.py` contract dump reports:
  - `theme_root`: `/home/pihole/zero2dash/themes`
  - `default_theme`: `default`
  - `active_theme`: `steele`
  - discovered themes: `carbon`, `comic`, `frosty`, `steele`
- `THEME_BUTTON_ORDER` in code is still:
  - `carbon`
  - `brushed_steel`
  - `comic_book`
  - `frosty`
- Actual theme directory ids are:
  - `carbon`
  - `comic`
  - `frosty`
  - `steele`
- The current code therefore still contains a naming mismatch between fixed theme button assignments and discovered theme ids.
- Shell back/return routing is still left-sided in `resolve_screen_action()` via `screen_x < MENU_STRIP_WIDTH`.
- Settings status rendering currently exposes these code constants:
  - `STATUS_TITLE_X = 20`
  - `STATUS_TITLE_Y = 18`
  - `STATUS_BODY_X = 20`
  - `STATUS_BODY_Y = 54`
  - `STATUS_LINE_SPACING = 14`
  - `STATUS_WRAP_WIDTH = 38`
- Settings status rendering still uses `ImageFont.load_default()`, so font path/choice and font size are not yet operator-tunable in code.
- No checked-in `tests/test_boot_selector.py` source file exists locally or on the device; only compiled `__pycache__` artifacts are present.

## Active Segments

- `S-001` control-plane reset: COMPLETE locally.
- `S-002` Themes verification: COMPLETE.
  Evidence:
  - actual installed theme ids verified from filesystem and `--dump-contracts`
  - actual button-order mismatch identified in code
- `S-003` Themes plus right-side back stripe implementation: IN PROGRESS.
  Completed in this segment:
  - `THEME_BUTTON_ORDER` now uses live ids and swaps `steele` and `frosty` while leaving the other working theme assignments intact
  Remaining work:
  - move the back stripe from left to right in shell routing
- `S-004` Settings layout stabilization and code-side tuning surface: OPEN.
  Verified remaining work:
  - improve text layout beyond current position-only constants
  - expose font choice/path and font size in code
  - make text area dimensions explicit
- `S-005` validation and closeout: OPEN.
  Verified remaining work:
  - determine whether test source files must be restored or created before meaningful regression coverage can be updated
  - record final `themes.png` deployment step on device

## Current Progress

- Local `PLAN.md` now reflects actual code findings instead of the stale markdown-only story.
- Local `AGENTS.md` has been narrowed to the active shell slice.
- The old supporting plan file has been removed locally to avoid split guidance.
- Device control-plane files remain outdated relative to the local control plane.

## Validation Snapshot

- Code inspection succeeded locally and on the device for the relevant `boot/boot_selector.py` sections.
- Device `python3 boot/boot_selector.py --dump-contracts --skip-gif --no-framebuffer` succeeded and exposed the live theme ids and shell contract.
- No new shell tests were run in this pass because the expected checked-in test source files are absent.

## Open Notes

- The key code-level issue for Themes is not theme discovery; it is the mismatch between discovered ids and the fixed preferred button-order ids.
- The key code-level issue for the back stripe is straightforward: all relevant shell screens still use the left edge.
- The key code-level issue for Settings is that position constants exist, but font and text-area tuning are still not surfaced cleanly.
