# Active Plan: NASA / ISS App Stabilization And Delivery

Status: ACTIVE
Date: 2026-03-28

The previous shell stabilization slice is complete and closed. This file is now the active execution contract for the standalone NASA / ISS app.

## Goal

Finish the existing `nasa-app/` implementation so it renders correctly, uses honest and useful data, starts quickly, and remains stable in the shell without broad shell refactors.

## Current Code Reality

The NASA app is not greenfield work. The repo already contains:

- a standalone app at `nasa-app/app.py`
- shell launch wiring in `boot/boot_selector.py`
- separate location and crew caches in `nasa-app/`
- safe preview and smoke-test modes
- a NASA-specific unittest file
- NASA page assets for map, details, crew, stale/error, and layout guidance

The job is to correct and stabilize what already exists.

## What Is Already Correct

- Shell launch wiring already exists and NASA is already routed from the root menu.
- The app already supports `--self-test`, `--page`, `--offline`, `--no-framebuffer`, and `--output`.
- The app already implements:
  - 10-second page cycling
  - 2-minute location refresh while running
  - crew pagination across overflow pages
  - separate `location_cache.json` and `crew_cache.json`
  - startup error rendering when no usable live/cache data exists
- The app already has a usable visual direction and does not need a full rewrite.
- Home/exit timing is already aligned at 2 seconds in the shell and the app.

## What Needs Fixing

- The map page uses the wrong assets today:
  - it loads `iss-background.png` instead of `map.png`
  - it uses the wrong stale/error asset path for the map flow
- Map plotting is not yet trustworthy against the real map artwork:
  - marker/trail drawing uses a generic box, not calibrated bounds for `map.png`
- Layout and operator-tuning are incomplete:
  - text/font/position controls are not clearly centralized and explained
- Crew rendering is broken:
  - the current crew page behavior can visually stack or overlap pages
- “Currently over” is not reliable today:
  - wrong background usage and brittle geocode handling can leave placeholder-like output
- Startup latency is too high:
  - current fetch flow blocks too much before a useful first frame is shown
- Flyover/pass-time support was previously degraded away:
  - this slice restores it if Open Notify pass lookup is usable

## API Decision

The current execution decision is:

- keep `wheretheiss.at` as primary for ISS position, telemetry, reverse geocoding, and trail
- keep Corquaid as primary for crew metadata
- use Open Notify for observer pass/flyover lookup
- keep Open Notify available as narrow fallback for `iss-now.json` and `astros.json` only where that already helps preserve degraded operation

Open Notify must not become the primary source for the whole app because it does not provide the rich telemetry and crew metadata this UI already expects. It is being used here specifically to restore observer pass/flyover behavior that was part of the original design.

If live pass lookup fails:

- show the last cached pass result if one exists
- mark it stale clearly
- otherwise show an honest unavailable state

## In Scope

- Stabilize the existing NASA app implementation in `nasa-app/`
- Correct map asset usage and map calibration
- Restore observer flyover/pass support using Open Notify if the endpoint is usable
- Reduce startup latency and add a loading screen so the app never sits blank for long
- Centralize and explain code-only layout/font controls for operator tuning
- Expand NASA-specific validation so acceptance is evidence-based
- Update repo-facing docs after runtime behavior is stable

## Out Of Scope

- No broad shell refactor
- No rotator integration for NASA
- No systemd or timer changes
- No new paid or key-based API without approval
- No speculative orbital math dependency such as `astropy` or `sgp4` without approval
- No unrelated Photos, Dashboards, or shell-theme work

## Runtime Contracts To Preserve

- `boot/boot_selector.py` remains the shell parent
- `nasa-app/app.py` remains a standalone child app
- NASA stays outside the module rotator
- existing shell launch path and page-1 bottom-left NASA routing stay intact unless device evidence proves otherwise
- NASA continues to support safe preview/testing without framebuffer writes

## Segments

### Segment 1: Contract Reset And Evidence Baseline

Status: OPEN

Goal:
- align the repo control plane to the active NASA slice and stop stale shell-slice guidance from competing with it

Files:
- `PLAN.md`
- `AGENTS.md`
- `coordination/tasks.md`
- `coordination/status.md`
- `coordination/decisions.md`
- `coordination/blockers.md`
- `task_plan.md`

Tasks:
- mark the previous shell slice complete
- record the active NASA defects and priorities
- lock the API and loading strategy decisions
- record the delegation/ownership model

Acceptance:
- the active plan matches the real NASA codebase and the operator decisions
- coordination no longer describes the finished shell slice as active

### Segment 2: Data Contract And Flyover Restoration

Status: OPEN

Goal:
- make the NASA app honest and stable about the data it shows, including restored observer pass times

Files:
- `nasa-app/app.py`
- `nasa-app/tests/test_nasa_app.py`

Tasks:
- keep `wheretheiss.at` as primary location source
- keep Corquaid as primary crew source
- add Open Notify pass/flyover lookup using the observer coordinates
- keep cached stale pass data available when live lookup fails
- tighten the location/crew/pass cache schema so inherited fields are explicit and safe
- review stale-state computation for map, details, crew, and pass display

Acceptance:
- primary and fallback sources are explicit in code
- live or cached observer pass data is shown honestly
- stale behavior matches the data actually shown on each page

### Segment 3: Rendering, Layout, And Map Accuracy

Status: OPEN

Goal:
- correct the visible NASA pages without rewriting the app

Files:
- `nasa-app/app.py`
- `nasa-app/assets/*` only if current art proves insufficient

Tasks:
- switch the map page to `map.png`
- switch the stale/error map page to the correct map-error asset
- calibrate marker/trail drawing to the visible world-map bounds inside `map.png`
- centralize all text/layout/font controls in one clearly labeled code block
- add short comments that explain what to edit for manual layout changes
- fix crew page overlap so only one page is drawn at a time
- add clear crew page position indicators
- tighten the details layout to reduce clipping risk
- make “Currently over” come from rendered data, not asset placeholders

Acceptance:
- map marker and trail align to the visible map art
- map page uses the correct assets
- crew pages do not overlap
- operator-tunable layout values are easy to find and understand in code
- the page set remains 320x240-safe without scrolling

### Segment 4: Startup Speed And Loading Experience

Status: OPEN

Goal:
- stop long blank startup waits

Files:
- `nasa-app/app.py`
- `nasa-app/assets/*` for a loading image if needed

Tasks:
- stop blocking the first visible frame on the full live fetch chain
- load cache immediately and render from cache if usable
- show a dedicated loading screen immediately if no usable page is ready yet
- defer non-critical fetches behind the first frame where safe
- reduce perceived and real startup delay as far as practical

Acceptance:
- the app shows a useful first frame quickly
- a loading screen exists if the app still needs time to resolve live data
- startup no longer feels like a long blank stall

### Segment 5: Runtime And Env Fixes

Status: OPEN

Goal:
- remove avoidable runtime fragility

Files:
- `nasa-app/app.py`
- `framebuffer.py` only if shared helper reuse is adopted

Tasks:
- stop hardcoding `.env` loading to `~/zero2dash/.env` when the repo root is already known
- use observer coordinates consistently for pass/flyover logic
- remove accidental duplicate module execution in the NASA tests
- reduce duplicated framebuffer logic if a minimal shared reuse path is safe
- avoid import-time failure for malformed framebuffer env values where practical

Acceptance:
- NASA config loading works in repo-local and deployed paths
- observer handling is used correctly
- duplicate test execution is gone
- runtime/setup behavior is less fragile than today

### Segment 6: Validation, Shell Verification, And Docs

Status: OPEN

Goal:
- close the slice with minimal shell risk and accurate docs

Files:
- `nasa-app/tests/test_nasa_app.py`
- optional `nasa-app/tests/*` fixtures
- `boot/boot_selector.py` only if shell evidence demands a change
- `README.md`
- `docs/wiki/Validation.md`
- `nasa-app/README.md`

Tasks:
- add tests for live/fallback/offline resolution branches
- add direct render checks for map, crew, loading, and error paths
- add pass-cache and stale-pass validation
- verify that the visible NASA tile still matches the live page-1 bottom-left route
- update README/wiki/NASA README to match the finished runtime and validation story

Acceptance:
- NASA tests cover current core branches, not just smoke paths
- shell launch path is confirmed
- no unnecessary shell edits were made
- repo-facing NASA docs match the final implementation and validation flow

## File Ownership / Edit Scopes

- NASA runtime and data logic:
  - `nasa-app/app.py`
- NASA tests:
  - `nasa-app/tests/test_nasa_app.py`
- NASA assets only if required:
  - `nasa-app/assets/*`
- Shell only if evidence requires it:
  - `boot/boot_selector.py`
- Docs after behavior is stable:
  - `README.md`
  - `docs/wiki/Validation.md`
  - `nasa-app/README.md`

## Risks

- `wheretheiss.at`, Corquaid, or Open Notify may be intermittently unreliable, so fallback and stale-state behavior must be robust
- the app already works partially, so careless refactoring could regress working behavior
- shell edits are higher-risk than NASA-local edits and should stay minimal
- current tests do not yet protect all important runtime branches

## Acceptance Mapping

- standalone NASA app remains outside the rotator
  - implementation: `nasa-app/app.py`, `boot/boot_selector.py`
- map page uses correct art and calibrated plotting
  - implementation: `nasa-app/app.py`, `nasa-app/assets/*`
- primary/fallback/pass data stack is explicit and honest
  - implementation: `nasa-app/app.py`
- live or cached observer pass data is shown honestly
  - implementation: `nasa-app/app.py`, `nasa-app/README.md`
- map/details/crew/loading/error pages render correctly in safe preview mode
  - implementation: `nasa-app/app.py`
  - verify: `--page ... --no-framebuffer --output ...`
- NASA config and observer loading work in real repo paths
  - implementation: `nasa-app/app.py`
- NASA tests cover major fallback, rendering, and startup branches
  - implementation: `nasa-app/tests/test_nasa_app.py`
- shell launch route remains correct
  - implementation: `boot/boot_selector.py` only if needed
  - verify: selector route review and later device confirmation
- docs match the final runtime and validation story
  - implementation: `README.md`, `docs/wiki/Validation.md`, `nasa-app/README.md`

## Execution Order

1. Segment 1: Contract reset and evidence baseline
2. Segment 2: Data contract and flyover restoration
3. Segment 3: Rendering, layout, and map accuracy
4. Segment 4: Startup speed and loading experience
5. Segment 5: Runtime and env fixes
6. Segment 6: Validation, shell verification, and docs

Segments 2 through 5 all center on `nasa-app/app.py` and `nasa-app/tests/test_nasa_app.py`, so implementation should stay serial there.

## Definition Of Done

This slice is done when:

- the active NASA data sources are explicit and defensible
- observer pass/flyover is restored or honestly degraded to cached/unavailable behavior
- the map page uses the right art and accurate plotting
- the existing pages are stable and readable
- startup no longer leaves the display blank for too long
- config loading and stale handling are corrected
- NASA-specific tests cover the important runtime branches
- shell launch behavior is verified with minimal or no shell edits
- repo-facing docs match the finished implementation
