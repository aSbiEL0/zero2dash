# NASA / ISS Delegation Plan

## Mission Brief

- Active slice: NASA / ISS app stabilization and delivery.
- Preserve dashboards, Photos, and systemd/autostart behavior.
- Keep shell edits minimal and evidence-driven.
- Serialise runtime edits to `nasa-app/app.py` and `nasa-app/tests/test_nasa_app.py`.

## Team Model

- `Pathfinder`
  - read-only discovery, fixture mapping, and targeted follow-up inspection
- `Switchboard`
  - owns NASA runtime implementation in `nasa-app/app.py`
- `Sentinel`
  - owns NASA tests, validation matrix, and acceptance evidence
- `Curator`
  - owns README/wiki/NASA README updates after runtime behavior is stable
- `Framekeeper`
  - reserve-only asset support if existing NASA art cannot support the agreed behavior

## Execution Order

1. `Pathfinder`
   - verify current map-asset paths, pass/flyover endpoint assumptions, cache schema, and any exact fixture points needed for tests
2. `Switchboard`
   - implement data/flyover/runtime fixes in `nasa-app/app.py`
   - implement rendering/layout/startup fixes in the same serial pass
3. `Sentinel`
   - expand NASA tests and validation commands after runtime code stabilizes
4. `Curator`
   - update docs after behavior and validation are locked
5. `Framekeeper`
   - only if runtime evidence shows the current map/loading assets are insufficient

## File Ownership

- `Switchboard`
  - `nasa-app/app.py`
  - `nasa-app/assets/*` only if runtime-owned asset changes are unavoidable
- `Sentinel`
  - `nasa-app/tests/test_nasa_app.py`
  - optional `nasa-app/tests/*` fixtures
- `Curator`
  - `README.md`
  - `docs/wiki/Validation.md`
  - `nasa-app/README.md`
- `Framekeeper`
  - `nasa-app/assets/*` only when explicitly activated

## Handoff Requirements

Every handoff must end with:
1. files changed
2. checks run
3. assumptions
4. blockers
5. next recommended owner

## Acceptance Targets

- map page uses `map.png` plus calibrated plotting
- crew page no longer overlaps and shows clear page position
- text/layout/font controls are clearly centralized and explained
- observer pass/flyover is restored with cached stale fallback
- startup shows a useful first frame quickly, with loading art if needed
- NASA tests cover the critical runtime branches
- docs match the final runtime and validation story
