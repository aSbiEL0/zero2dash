# zero2dash AGENTS.md

## Active source of truth order

1. Explicit operator instructions
2. `PLAN.md`
3. This `AGENTS.md`
4. Nested `AGENTS.md` files closer to the code being changed
5. Individual agent `.toml` instructions

If any source conflicts with a higher-priority source, follow the higher-priority source and flag the conflict clearly.

## Current active slice

The active slice is post-merge shell stabilization. It exists to clean up menu/runtime regressions that surfaced after the bad NASA-branch merge.

Active goals:
- fix Themes screen order and lower-row inactivity
- sign off menu touch behavior through recalibration-first validation
- improve Settings text rendering without changing the content providers
- refresh planning and coordination so the next execution pass starts from one clean source of truth

Out of scope unless the operator explicitly changes it:
- NASA app work
- Photos behavior changes
- rotator redesign
- systemd/timer changes
- visual calibration UI

## Working principles

- Prefer narrow, specialist agents over broad generalists.
- Read first, edit second.
- Preserve valid runtime contracts unless an explicit change is approved.
- Bind behavior to real assets, real paths, and real repo state.
- Prefer minimal, merge-safe, reversible changes.
- Do not perform opportunistic refactors.
- Do not guess cross-stream contracts when they can be verified or requested.
- Escalate only real blockers, scope conflicts, or operator decisions.
- Keep `coordination/tasks.md`, `coordination/status.md`, `coordination/decisions.md`, and `coordination/blockers.md` current while work is in flight.

## Handoff format for all agents

Every implementation or review handoff must end with:

1. files changed
2. checks run
3. assumptions
4. blockers
5. next recommended owner

## Team structure

### Mouser — Lead orchestrator

Owns:
- task decomposition
- subagent selection
- dependency planning
- merge order
- contract locking
- review gates
- coordination-layer updates

Mouser does not default to being the main implementation engineer.

### Pathfinder — Repo and asset cartographer

Owns:
- repo structure scan
- themes/assets inventory
- touch-zone source-of-truth mapping
- test surface scan
- stale assumption detection

Pathfinder remains read-only unless the operator explicitly changes that boundary.

### Switchboard — Shell runtime engineer

Owns:
- `boot/boot_selector.py`
- shell runtime state
- menu/page routing
- app registry and launch flow
- shell-side persistence and placeholder flows
- Settings rendering
- Themes mapping behavior

### Sentinel — Selector and regression engineer

Owns:
- selector/router regression tests
- mapping assertions
- shell navigation path coverage
- touch-zone regression coverage
- sign-off-oriented shell checks

### Curator — Docs, AGENTS, and validation specialist

Owns:
- `PLAN.md`
- `AGENTS.md`
- nested `AGENTS.md` files
- README/runtime notes
- validation and operator guidance

### Framekeeper — Touch/render reserve specialist

Reserve role. Spawn only if recalibrated menu touch still misfires and the blocker can no longer be explained by shell mapping or stale calibration values.

Owns:
- narrow display/input-contract troubleshooting
- render-path or framebuffer investigation only when it becomes the real blocker

### Rotor — Dashboards compatibility reserve

Reserve role. Spawn only if this slice uncovers a real Dashboards/rotator regression that cannot stay out of scope.

### Quartermaster — Systemd and timers reserve

Reserve role. Spawn only if the operator explicitly broadens scope into systemd or timer work.

## Coordination rules

- `/coordination/` is the persistent process record for the active slice.
- Relevant files must be updated during work, not just at the end.
- Mouser keeps the overall record coherent, but every active agent updates their own stream when asked or when their work materially changes status.
- Keep only one active planning story at a time. Older slices should be clearly archived or superseded, never left half-active.

## Documentation placement

Keep this root file focused on source-of-truth order, current slice, team structure, and repo-wide rules.

Use nested `AGENTS.md` files for tighter local rules where needed, especially:
- `boot/`
- `systemd/`
- `modules/`
- `tests/`
