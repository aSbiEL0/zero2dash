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
- Theme routing has been corrected locally and confirmed on hardware.
- Shell back/return routing now uses the rightmost `20px` strip and has been confirmed on hardware.
- Settings status rendering now exposes an explicit code-side tuning block for:
  - title `x`, `y`, width, height, font path, and font size
  - body `x`, `y`, width, height, font path, and font size
  - line spacing and bottom margin
- Settings status rendering now uses explicit font loading and pixel-width wrapping/truncation instead of `ImageFont.load_default()` plus character-count wrapping.
- No checked-in `tests/test_boot_selector.py` source file exists locally or on the device; only compiled `__pycache__` artifacts are present.

## Active Segments

- `S-001` control-plane reset: COMPLETE locally.
- `S-002` Themes verification: COMPLETE.
  Evidence:
  - actual installed theme ids verified from filesystem and `--dump-contracts`
  - actual button-order mismatch identified in code
- `S-003` Themes plus right-side back stripe implementation: COMPLETE.
  Completed in this segment:
  - `THEME_BUTTON_ORDER` now uses live ids and swaps `steele` and `frosty` while leaving the other working theme assignments intact
  - on-device confirmation received that the Themes swap works correctly
  - shell routing now treats the rightmost `20px` as the strip hit area and uses the remaining `300px` as the active content width for stripe-based screens
  - on-device confirmation received that the right-side stripe matches the updated touch-mapping references
- `S-004` Settings layout stabilization and code-side tuning surface: OPEN.
  Current state:
  - local code now exposes the Settings/status layout knobs in `boot/boot_selector.py`
  - local code now uses explicit title/body widths and heights plus font path/size controls
  - hardware confirmation is still pending
- `S-005` validation and closeout: OPEN.
  Verified remaining work:
  - determine whether test source files must be restored or created before meaningful regression coverage can be updated
  - record final `themes.png` deployment step on device

## Current Progress

- Local `PLAN.md` now reflects actual code findings instead of the stale markdown-only story.
- Local `AGENTS.md` has been narrowed to the active shell slice.
- The old supporting plan file has been removed locally to avoid split guidance.
- Segment `S-004` is now in active implementation with local code changes ready for device verification.
- Device control-plane files remain outdated relative to the local control plane.

## Validation Snapshot

- Code inspection succeeded locally and on the device for the relevant `boot/boot_selector.py` sections.
- Device `python3 boot/boot_selector.py --dump-contracts --skip-gif --no-framebuffer` succeeded and exposed the live theme ids and shell contract.
- No new shell tests were run in this pass because the expected checked-in test source files are absent.

## Open Notes

- The remaining open runtime question is whether the new Settings layout defaults look correct on hardware.
- If further tuning is needed, the values to edit now live together near the top of `boot/boot_selector.py`.
- Regression source files for shell behavior are still missing, so final validation remains partly device-led.
