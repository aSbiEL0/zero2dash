# PLAN Archive: Shell Repair + Asset-Backed Menu Rebuild

Status: COMPLETE
Archived: 2026-03-19

This plan is complete and retained as an archive record for the finished shell-repair slice.
It is no longer the active execution plan for new work. The next plan should replace this file
or clearly supersede it before additional implementation starts.

## Completion Summary

- The shell baseline was repaired and the selector was rebuilt against the real theme asset tree.
- `boot/boot_selector.py` remained the parent shell.
- `display_rotator.py` remained the Dashboards child entrypoint.
- `modules/photos/slideshow.py` remained the Photos child entrypoint.
- ADS7846 touch fallback, child launch regressions, keypad routing, and consecutive PIN-failure behavior were fixed to a usable Pi baseline.
- Coordination, README, and wiki docs were updated to match the landed runtime.

## Summary

- Repair the currently broken shell baseline first, then land the menu rebuild against the actual uploaded asset tree in [themes](/C:/Users/Default.DESKTOP-MR88P09/.codex/zero2dash/themes).
- Keep the stable runtime contracts intact:
  - [boot/boot_selector.py](/C:/Users/Default.DESKTOP-MR88P09/.codex/zero2dash/boot/boot_selector.py) remains the parent shell
  - [display_rotator.py](/C:/Users/Default.DESKTOP-MR88P09/.codex/zero2dash/display_rotator.py) remains the Dashboards child entrypoint
  - [modules/photos/slideshow.py](/C:/Users/Default.DESKTOP-MR88P09/.codex/zero2dash/modules/photos/slideshow.py) remains the Photos child entrypoint
  - shell modes remain `menu`, `dashboards`, `photos`, `night`
- Replace the old Video slot with the NASA ISS slot everywhere. The uploaded `mainmenu1.png` assets already do this visually.

## Actual Asset Contract

Theme assets live under [themes](/C:/Users/Default.DESKTOP-MR88P09/.codex/zero2dash/themes), one directory per theme. Current theme IDs are:

- `default`
- `comic`
- `steele`

Each theme directory currently provides this real on-disk asset set:

- `mainmenu1.png`
- `mainmenu2.png`
- `day-night.png`
- `themes.png`
- `settings.png`
- `stats.png`
- `yes-no.png`
- `keypad.png`
- `granted.gif`
- `denied.gif`

Shared non-theme assets remain under [boot](/C:/Users/Default.DESKTOP-MR88P09/.codex/zero2dash/boot):

- `startup.gif`
- `credits.gif`

The plan should stop inventing per-screen names like `shutdown_confirm.png` or per-status files like `network_status.png`. The shell must bind to the uploaded names above.

## Screen and Touch Behavior

### Baseline repair

- Remove the committed merge-conflict state from [display_rotator.py](/C:/Users/Default.DESKTOP-MR88P09/.codex/zero2dash/display_rotator.py) and restore one valid Dashboards runtime path.
- Add selector-focused tests so menu regressions stop slipping through.

### Root screens

`main_menu_1` uses `mainmenu1.png` and the 4-button layout:
- top-left: Dashboards
- top-right: Photo Slideshow
- bottom-left: NASA ISS
- bottom-right: Locked Content

`main_menu_2` uses `mainmenu2.png` and the 4-button layout:
- top-left: Credits
- top-right: Themes
- bottom-left: Settings
- bottom-right: Shutdown

Root strip behavior:
- the 20px left strip switches between `main_menu_1` and `main_menu_2`
- session return to menu restores the last visited root page
- restart does not persist last root page

### Child menus

`dashboards_menu` uses `day-night.png` and the 2-button layout:
- top: Dashboards
- bottom: Night Mode
- strip: Back to `main_menu_1`

`settings_menu` uses `settings.png` and the 3-button layout:
- top: Network
- middle: Pi Stats
- bottom: Logs
- strip: Back to `main_menu_2`

`shutdown_confirm` uses `yes-no.png` and the 2-button layout:
- top: Confirm shutdown
- bottom: Cancel
- strip: Cancel

`pin_keypad` uses `keypad.png` and the full-screen 4x3 keypad layout with no strip.

### Status and placeholder screens

- `network_status`, `pi_stats_status`, `logs_status`, and `iss_placeholder` share `stats.png` as the base asset.
- These screens are display-first and strip-only:
  - strip: Back
  - main content area: no touch actions
- Overlay screen-specific text/data onto the content area of `stats.png`.
- Each screen must render a clear unavailable/error state when data is missing.

### Credits and PIN result flows

- Credits uses the shared `credits.gif`.
- Any tap skips Credits and returns to `main_menu_2`.
- `access_granted` uses the active theme’s `granted.gif`, auto-advances to the current locked-content command, then returns to menu when the child exits.
- `access_denied` uses the active theme’s `denied.gif`, auto-returns to menu.
- Third consecutive PIN failure keeps the current shutdown behavior.

## Theme Behavior

- Discover the theme registry from the directories under [themes](/C:/Users/Default.DESKTOP-MR88P09/.codex/zero2dash/themes), not from a hardcoded list.
- The theme picker screen uses `themes.png`.
- The uploaded `themes.png` art should be treated as three theme columns, not six independent themes:
  - left column selects `default`
  - middle column selects `steele`
  - right column selects `comic`
  - tapping either the top or bottom cell in a column selects that same theme
- Persist theme selection only.
- On first boot with no saved value, use an explicit configured default theme.
- Theme apply behavior:
  - save immediately
  - re-render immediately
  - remain on the Themes screen

## Runtime Compatibility

- `startup.gif` plays once at process start only.
- `menu` mode request returns to the last visited root page in the current session, defaulting to `main_menu_1`.
- `dashboards`, `photos`, and `night` mode requests still launch the existing child targets directly.
- Photos still launches directly from `main_menu_1`.
- NASA ISS remains a shell-owned placeholder in this slice; the separate app is out of scope.

## Tests

- Add selector/router tests for:
  - `mainmenu1.png` and `mainmenu2.png` zone-to-action mapping
  - root strip switching between both root pages
  - `day-night.png` mapping to Dashboards and Night
  - `settings.png` mapping to Network, Pi Stats, and Logs
  - `yes-no.png` mapping with strip-as-cancel
  - theme discovery from the real `themes/*` directories
  - `themes.png` column mapping where both cells in a column select one theme
  - `stats.png` shared-base rendering for Network, Pi Stats, Logs, and ISS placeholder
  - startup GIF boot-only gating
  - Credits tap-to-skip behavior
  - keypad success, failure, cancel, and third-failure shutdown path
- Add repair validation that the selector can launch [display_rotator.py](/C:/Users/Default.DESKTOP-MR88P09/.codex/zero2dash/display_rotator.py) again.

## Assumptions

- `themes/default/1.png` is currently unbound and should be ignored unless you explicitly assign it a role.
- `stats.png` is a reusable status/placeholder frame, not a Pi-Stats-only asset.
- If a required theme asset is missing from the selected theme directory, validation should fail loudly rather than silently falling back to the old generic menu.
