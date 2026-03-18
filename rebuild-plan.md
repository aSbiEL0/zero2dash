# Rebuild Plan: Architecture Remediation

## Summary

The shell-first runtime is now the baseline, not the target. This rebuild focuses on making that baseline maintainable, testable, and operationally safer by reducing rotator complexity, centralizing framebuffer logic, normalizing failures, hardening systemd behavior, and documenting the real architecture.

The rebuild must proceed in small, merge-safe slices. Prefer behavior-preserving refactors first. Do not use this rebuild to add new user-facing features.

## Current Rebuild State

Completed:
- control-plane cleanup is done
- the accepted baseline remediation slice (`616c169`) is in place
- rotator touch and screen-power internals have been extracted
- framebuffer helpers have been consolidated into `framebuffer.py`
- service-boundary documentation and refresh-service hardening have landed
- rebuild docs and validation guidance have been refreshed
- shell registry, lifecycle, and mode-switch contracts have been recorded

Still required:
- normalize failure semantics and exit codes across the runtime
- review remaining service/runtime coupling on real hardware
- run final Pi validation against the intended selector/menu behavior
- keep menu redesign and other feature ideas out of scope unless explicitly promoted

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

## Remaining Delivery
### Step 1. Normalize failure semantics

- return non-zero for genuine render or refresh failures
- ensure self-tests fail loudly on real errors
- preserve rotator backoff and quarantine protections

### Step 2. Confirm service and privilege boundaries on hardware

- confirm refresh/update jobs remain independent on the Pi
- verify service-user and device-access expectations are correct in deployment
- verify foreground framebuffer ownership stays non-competing in practice

### Step 3. Expand tests where extracted logic now allows it

- add deterministic tests for extracted rotator components
- add or extend framebuffer conversion tests
- add tests around failure semantics where logic is now isolated
- reserve Pi-only checks for final integration validation

### Step 4. Final docs and validation closeout

- document the real current architecture, not the old migration intent
- add operator guidance for runtime checks, service checks, and rollback paths
- keep feature ideas and future enhancements explicitly out of scope

## Merge Order

1. Failure-semantics slice
2. Hardware validation and service verification
3. Targeted test expansion
4. Final docs closeout

## Acceptance Criteria

- `display_rotator.py` remains an entrypoint, not a monolith for touch/power internals
- framebuffer conversion and write logic is single-source for supported module paths
- module and service failures signal failure consistently
- refresh/update services no longer depend on obsolete foreground-runtime assumptions
- hardware-free tests cover the extracted logic that was actually isolated
- docs and coordination files describe the actual rebuild state accurately
