# Rebuild Plan: Architecture Remediation

## Summary

The shell-first runtime is now the baseline, not the target. This rebuild focuses on making that baseline maintainable, testable, and operationally safer by reducing rotator complexity, centralizing framebuffer logic, normalizing failures, hardening systemd behavior, and documenting the real architecture.

The rebuild must proceed in small, merge-safe slices. Prefer behavior-preserving refactors first. Do not use this rebuild to add new user-facing features.

## Goals

- decompose `display_rotator.py` into clearer internal modules
- make framebuffer and RGB565 handling single-source
- normalize error handling and exit codes
- harden foreground-service and refresh-service behavior
- expand hardware-free test coverage
- replace stale migration-focused docs with architecture and operator docs

## Non-goals

- no rollback of the shell-first baseline unless a concrete regression demands it
- no broad UI redesign
- no new feature streams such as Videos during this rebuild
- no speculative dependency additions without explicit approval

## Team Split

### Relay

Owns rotator decomposition.

Scope:
- `display_rotator.py`
- `rotator/*`
- rotator-focused tests

### Iris

Owns framebuffer and rendering consolidation.

Scope:
- `framebuffer.py`
- image-producing module migrations
- framebuffer-focused tests

### Forge

Owns systemd hardening and runtime-service boundaries.

Scope:
- `systemd/*`
- service interaction docs where needed

### Atlas

Owns compatibility guardrails and cross-stream runtime review.

Scope:
- shell compatibility review
- minimal shell fixes only if remediation exposes a real contract defect

### Quill

Owns docs, validation guidance, and architecture visibility.

Scope:
- `README.md`
- `AGENTS.md`
- validation and operator docs

### Merlin

Owns coordination, sequencing, task slicing, and review.

## Step-by-Step Delivery

### Step 1. Reset the control plane

- replace stale stream-completion status with a live remediation status
- replace stale task board entries with remediation tasks
- mark `PLAN.md` historical and make `rebuild-plan.md` active
- keep feature ideas in `coordination/ideas.md`, but out of scope

### Step 2. Accept the first remediation slice

- use branch `codex/architecture-remediation` and commit `616c169` as the starting point
- treat `framebuffer.py` and `rotator/*` as real baseline code, not scratch work
- preserve `display_rotator.py` as the public dashboards entrypoint

### Step 3. Finish rotator decomposition

- extract touch handling from `display_rotator.py`
- extract screen-power control from `display_rotator.py`
- keep entrypoint behavior and dashboard flow stable
- move control-path status output toward structured logging at the runner boundary

### Step 4. Finish framebuffer consolidation

- migrate remaining modules away from duplicate RGB565/framebuffer helpers
- remove duplicate conversion logic where practical
- keep hardware output behavior stable

### Step 5. Normalize failure semantics

- return non-zero for genuine render or refresh failures
- ensure self-tests fail loudly on real errors
- preserve rotator backoff and quarantine protections

### Step 6. Harden services and privilege boundaries

- remove hidden dependence on obsolete foreground services
- ensure refresh/update jobs remain independent
- make service-user and device-access expectations explicit
- keep foreground ownership of the framebuffer non-competing

### Step 7. Expand tests

- add deterministic tests for extracted rotator components
- add or extend framebuffer conversion tests
- add tests around failure semantics where logic is now isolated
- reserve Pi-only checks for final integration validation

### Step 8. Final docs and validation

- document the real current architecture, not the old migration intent
- add operator guidance for runtime checks, service checks, and rollback paths
- keep feature ideas and future enhancements explicitly out of scope

## Merge Order

1. Control-plane cleanup
2. Relay and Iris in parallel on disjoint internals
3. Atlas compatibility review
4. Forge systemd hardening
5. Quill final docs and validation pass

## Acceptance Criteria

- `display_rotator.py` is materially smaller in responsibility even if it remains the entrypoint
- framebuffer conversion and write logic is single-source for supported module paths
- module and service failures signal failure consistently
- refresh/update services no longer depend on obsolete foreground-runtime assumptions
- hardware-free tests cover the extracted logic
- docs and coordination files describe the actual rebuild state accurately
