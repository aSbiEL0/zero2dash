# Project Status

Last updated: 2026-03-28

Live status: ACTIVE

## Active Execution State

- The completed shell stabilization slice is now historical.
- The active slice is NASA / ISS app stabilization and delivery.
- Dashboards, Photos, and systemd/autostart remain preserved unless the operator explicitly reopens them.
- Shell-first runtime remains accepted:
  - `boot/boot_selector.py` is the parent shell
  - `display_rotator.py` remains the dashboards entrypoint
  - `modules/photos/slideshow.py` remains the Photos entrypoint
  - `nasa-app/app.py` remains a standalone child app

## Verified NASA Reality

- NASA launch wiring already exists in `boot/boot_selector.py`.
- The root menu already routes the page-1 bottom-left tile to NASA.
- The NASA app already supports safe preview and self-test modes.
- The app already has separate location and crew caches.
- The current app is partially stabilized, and the remaining defects are now narrower:
  - startup still needs device confirmation after the new loading-and-cache-first fix
  - flyover/pass support still needs restoring
  - final automated validation is blocked locally by a broken Python install

## Active Segments

- `N-001` control-plane reset: COMPLETE.
- `N-002` NASA discovery baseline: COMPLETE.
- `N-003` NASA runtime fixes: IN PROGRESS.
  Completed in the current slice:
  - map assets switched to `map.png` / `map-error.png`
  - plotting moved to explicit configured map bounds
  - map geometry now matches the new guide-derived contract: full-width band at `x=0, y=40, width=320, height=160`
  - operator-editable layout/font controls centralized in `nasa-app/app.py`
  - details and crew layouts now target the new guide-derived `260x180` text box at `x=30, y=30`
  - crew page now renders a visible page badge
  - `Currently over` now sanitizes placeholder cache values like `??` instead of treating them as valid location data
  - startup now renders an immediate loading frame before live fetch work on hardware paths
  - startup now prefers usable cached location over Open Notify as the first fallback after live failure
  - crew is no longer part of the first-frame readiness gate; cached crew renders first and live crew refreshes after the first frame
  - crew pages now render a stronger `Crew x/y` header and wider row spacing for clearer per-page separation
  Remaining:
  - pass/flyover restoration
  - device validation for the new startup/loading and crew-page clarity pass
- `N-004` NASA validation expansion: IN PROGRESS.
  Completed in the current slice:
  - duplicate NASA test-module execution removed
  - deterministic render-path tests added for map asset routing, details display-name use, crew badge labeling, and overflow sequencing
  - regression tests now cover placeholder-location sanitization and `Currently over` fallback handling
  - regression tests now cover the new map-band constants, anchor-point mapping, and guide-box constants
  - regression tests now cover loading-screen asset selection
  - regression tests now cover the cache-before-open-notify startup policy
  Remaining:
  - run the automated checks in a working Python environment
  - add tests for later pass/flyover and loading behavior after those features land
- `N-005` NASA docs alignment: QUEUED.
- `N-006` asset support: CONDITIONAL.

## Current Progress

- `PLAN.md` now reflects the NASA slice, not the completed shell slice.
- `AGENTS.md` now points at NASA stabilization as current priority.
- The first runtime correction slice in `nasa-app/app.py` is review-clean.
- The first deterministic NASA test slice in `nasa-app/tests/test_nasa_app.py` is review-clean.
- The asset-contract reset for the new `Downloads\\iss` pack is now implemented locally in code and assets, pending device validation.
- NASA-specific control-plane decisions are now explicit:
  - `wheretheiss.at` remains primary telemetry
  - Corquaid remains primary crew source
  - Open Notify is used to restore observer pass/flyover behavior
  - cached stale pass data is preferred over blanking the feature entirely
  - startup should show a useful first frame quickly, with a loading screen if needed

## Validation Snapshot

- Current NASA validation surface is stronger than before, but it is still not final.
- What exists now:
  - `nasa-app/app.py --self-test`
  - page preview rendering via `--page ... --no-framebuffer --output ...`
  - a NASA-specific unittest file with deterministic render-path coverage for the first runtime slice
- What is still missing:
  - pass-cache and stale-pass coverage
  - loading/runtime branch coverage after the loading slice lands
  - final device validation evidence for the corrected NASA behavior
  - a working local Python interpreter in this workspace for direct automated execution

## Open Notes

- Shell changes are expected to be minimal or unnecessary unless device evidence proves the visible NASA tile/launch contract is wrong.
- Existing NASA assets may be usable after runtime fixes; asset replacement is conditional, not assumed.
- Local attempts to run `C:\ISS\.venv\Scripts\python.exe` fail because it resolves to `...\Python313\python.exe` and returns `Access is denied`.
