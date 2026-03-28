# Blockers

Live status: RESET on 2026-03-28.

Rules:
- Any agent may log a blocker.
- Mouser decides resolution.
- Only Mouser may mark a blocker resolved.

---

## Current State

- Active NASA blockers are recorded below.

---

BLOCKER ID: B-004
Status: RESOLVED

Topic:
Map page uses the wrong assets and uncalibrated plotting

Details:
- `render_map_page()` currently uses `iss-background.png` instead of `map.png`.
- marker/trail plotting uses a generic box and is not calibrated to the visible map art.

Impact:
- the location page does not meet the intended map contract
- users cannot trust the apparent position/trail against the displayed map

Workaround:
- none that is good enough for sign-off

Unblock condition:
- map page uses the correct map art and calibrated plotting bounds

Resolution notes:
- `nasa-app/app.py` now points the map page at `map.png` / `map-error.png`
- map plotting now uses explicit configured overlay bounds instead of the old generic box

---

BLOCKER ID: B-005
Status: ACTIVE

Topic:
Startup latency and blank-load experience

Details:
- the app currently blocks too much work before showing a useful first frame
- the operator reports startup often feels like a 7-10 second wait

Impact:
- the app feels broken or hung during launch
- poor startup perception reduces confidence even when the app later recovers

Workaround:
- none acceptable for final acceptance

Unblock condition:
- the app shows a useful first frame quickly from cache or a loading screen, with reduced blocking startup work

---

BLOCKER ID: B-006
Status: RESOLVED

Topic:
Crew page rendering overlap

Details:
- the operator reports the crew page displays two pages on top of each other
- current crew rendering and pagination state must be corrected before sign-off

Impact:
- crew information is visually broken
- paginated crew output is not trustworthy as currently rendered

Workaround:
- none acceptable for final acceptance

Unblock condition:
- only one crew page renders at a time and page position is clear

Resolution notes:
- the crew renderer now draws a visible `page/total` badge
- the first runtime slice was review-cleaned after the renderer/layout changes

## Logging Rule

---

BLOCKER ID: B-007
Status: ACTIVE

Topic:
Local automated validation is blocked by the configured Python environment

Details:
- local attempts to run `C:\ISS\.venv\Scripts\python.exe` fail because it resolves to `...\Python313\python.exe` and returns `Access is denied`
- no `python`, `python3`, or `py` launcher is available on PATH in this sandbox

Impact:
- local execution of `nasa-app/app.py --self-test` and `nasa-app/tests/test_nasa_app.py` cannot be completed from this workspace right now
- automated validation evidence remains incomplete until a working interpreter path is available

Workaround:
- rely on code review plus device-side/operator validation for interim progress

Unblock condition:
- a working Python interpreter is available locally for the NASA app and test commands

Only log a blocker here if it is one of:
- a verified runtime or rendering mismatch against the current NASA contract
- a code-level data/routing mismatch that blocks sign-off
- a missing validation surface that prevents credible completion claims
