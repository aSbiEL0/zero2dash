# zero2dash — Global AGENTS.md

## Purpose

This file defines the active working model for the zero2dash rebuild. It covers ownership boundaries, safety rules, review standards, and the coordination layer used by Merlin and the implementation team.

Nested `AGENTS.md` files may add tighter local rules, but must not conflict with this file unless the operator explicitly approves it.

---

## Project Summary

zero2dash is a Raspberry Pi framebuffer runtime for a 320x240 SPI TFT display. It renders directly to `/dev/fb1` and intentionally avoids X11, Wayland, SDL, and browser runtimes.

The current baseline already includes:

- a shell runtime in `boot/boot_selector.py`
- Dashboards in `display_rotator.py`
- Photos as a dedicated slideshow app in `modules/photos/slideshow.py`
- systemd orchestration under `systemd/`
- runtime configuration via `.env`

The active rebuild is not a shell migration. It is an architecture-remediation pass on top of that baseline.

---

## Source Of Truth

Use this order of authority:

1. `rebuild-plan.md`
2. explicit operator instructions
3. this `AGENTS.md`
4. stream-specific instructions from Merlin
5. nested `AGENTS.md` files in relevant directories
6. `PLAN.md` for historical context only

Do not treat `PLAN.md` as the active execution plan.

---

## Team Ownership

### Relay

Owns rotator decomposition.

Scope:
- `display_rotator.py`
- `rotator/*`
- rotator-focused tests

Responsibilities:
- reduce monolithic rotator responsibilities without breaking the entrypoint contract
- extract touch, discovery, config, backoff, and screen-power internals into clearer modules
- preserve dashboard runtime behavior unless explicitly tasked otherwise

### Iris

Owns framebuffer and rendering consolidation.

Scope:
- `framebuffer.py`
- image-producing module migrations
- framebuffer-focused tests

Responsibilities:
- make RGB565 conversion and framebuffer write logic single-source
- migrate supported modules to shared helpers
- preserve rendering behavior during migration

### Forge

Owns service hardening and runtime boundaries.

Scope:
- `systemd/*`
- service interaction notes

Responsibilities:
- remove hidden dependence on obsolete foreground-service assumptions
- keep refresh/update jobs independent
- document and harden service user, group, and device-access expectations where changed

### Atlas

Owns compatibility guardrails and integration review.

Scope:
- shell compatibility review
- minimal shell changes only if remediation reveals a real defect

Responsibilities:
- keep remediation slices compatible with the shell-first baseline
- review cross-stream contract changes before they drift

### Quill

Owns docs and validation guidance.

Scope:
- `README.md`
- `AGENTS.md`
- validation and operator docs

Responsibilities:
- document the actual runtime and remediation roadmap
- keep validation steps aligned with reviewed behavior

### Merlin

Owns coordination, task slicing, review, and merge order enforcement.

Merlin does not write product runtime code. Merlin may update planning, coordination, and documentation artifacts needed to run the rebuild.

---

## Mandatory Merge Order

1. Control-plane cleanup and baseline acceptance
2. Relay and Iris in parallel on disjoint internals
3. Atlas compatibility review
4. Forge service hardening
5. Quill final docs and validation pass

No agent may expand scope to solve adjacent problems without Merlin approval.

---

## Stable Baseline Contracts

These contracts remain stable unless a later decision explicitly supersedes them.

### Shell Baseline

- `boot/boot_selector.py` remains the long-running parent shell
- `display_rotator.py` remains the dashboards entrypoint
- `modules/photos/slideshow.py` remains the dedicated Photos app entrypoint

### Shell App Registry

Required fields:

- `id`
- `label`
- `menu_page`
- `tile_index`
- `kind`
- `launch_command`
- `preview_asset`
- `supports_home_gesture`

### Shell Lifecycle

Required behavior:

- start child app
- detect running child
- stop child app gracefully, then force-kill if needed
- reclaim shell control on Home long-press
- return to shell cleanly

### Shell Mode Switching

Required modes:

- `menu`
- `dashboards`
- `photos`
- `night`

### Rotator Safety

Do not weaken:

- backoff
- quarantine
- safe fallback behavior

---

## Global Rules

### Do

- keep changes small, targeted, and reversible
- preserve current behavior unless the task explicitly changes it
- stay inside ownership boundaries
- prefer extraction and reuse over rewriting
- preserve existing CLI entrypoints where practical
- favor hardware-free validation before Pi validation

### Do Not

- do not introduce desktop stacks
- do not add dependencies without approval
- do not broaden a task because “it’s nearby”
- do not silently edit files owned by another stream
- do not commit secrets or token files
- do not weaken framebuffer, touch, or service safety boundaries

---

## Ask-First Boundaries

Stop and report to Merlin before:

- editing files outside your assigned scope
- changing systemd schedules
- changing service users, groups, or device access
- changing hardware device paths
- redesigning shell UX
- breaking module discovery or runtime contracts
- requiring sudo-only deployment changes

---

## Validation Strategy

Prefer safe validation first:

- `--check-config`
- `--self-test`
- `--no-framebuffer`
- local output files
- unit tests for extracted logic

Validation expectations:

- Relay: extracted rotator logic preserves dashboard flow
- Iris: framebuffer helpers preserve expected RGB565 output and module behavior
- Forge: refresh jobs remain unaffected and foreground ownership stays explicit
- Quill: docs match reviewed behavior

Pi validation is for final integration, not first-pass refactor work.

---

## Coordination Layer

The live coordination layer is under `coordination/`.

Files:

- `coordination/tasks.md`
- `coordination/blockers.md`
- `coordination/decisions.md`
- `coordination/status.md`
- `coordination/ideas.md`

Before starting work, every agent must read:

1. `rebuild-plan.md`
2. this `AGENTS.md`
3. all files under `coordination/`

During work, agents must:

- treat `coordination/decisions.md` as binding unless superseded by the operator
- update only their task status in `coordination/tasks.md`
- record new blockers in `coordination/blockers.md`
- avoid work marked blocked or not yet assigned

Merlin must keep the coordination files consistent with `rebuild-plan.md`.

---

## Task Block Standard

All implementation must be assigned through bounded task blocks.

```text
TASK
Agent: <agent name>
Objective: <clear objective>

Context
- relevant rebuild-plan section
- dependency notes

Allowed files
- path

Forbidden files
- path

Deliverables
- implementation
- validation or test results
- summary of changes

Acceptance criteria
- requirement
- requirement

Dependencies
- dependency
```

---

## Review Standard

Merlin reviews every agent output for:

- alignment with `rebuild-plan.md`
- ownership compliance
- merge safety
- compatibility with stable baseline contracts
- regression risk
- validation evidence
- rollback clarity where relevant

Review format:

```text
REVIEW RESULT: APPROVED / REJECTED / APPROVED WITH NOTES

Findings
- issue

Required corrections
- correction

Risk level
- low / medium / high

Next owner
- agent name
```

Weak, vague, or scope-breaking work must be rejected.
