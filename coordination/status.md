# Stream Status

Last updated: 2026-03-14

## Overall

- Project state: baseline before shell-first migration
- Active branch for Merlin coordination: `merlin/coordination-setup`
- Current merge gate: Stream A contract lock must complete first

## Streams

### Stream A — Shell Runtime

- Owner: Atlas
- Status: READY
- Task: `T-001`
- Notes: Phase 1 contract lock and shell spine can start immediately

### Stream B — Dashboards App

- Owner: Relay
- Status: WAITING
- Dependency: Stream A contract lock
- Notes: Do not begin mergeable implementation until Atlas publishes the shell app lifecycle contract

### Stream C — Photos App

- Owner: Iris
- Status: WAITING
- Dependency: Stream A contract lock
- Notes: Reuse planning may begin later, but mergeable work waits on the child-app contract

### Stream D — systemd / Ops Transition

- Owner: Forge
- Status: BLOCKED
- Dependency: Stream A shell mode-switch interface
- Notes: Do not start timer or service rewiring yet

### Stream E — Docs / Migration / Validation

- Owner: Quill
- Status: WAITING
- Dependency: Final behavior from Streams A-D
- Notes: Final pass remains last; no runtime behavior may be invented in docs

## Merge Order

1. Stream A contract branch
2. Streams B and C after A contract lock
3. Stream A integration pass
4. Stream D after shell mode-switch path is stable
5. Stream E final pass
