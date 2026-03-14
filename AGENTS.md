# zero2dash — Global AGENTS.md

## Purpose

This file is the global instruction hub for the zero2dash multi-agent team. It defines the project runtime model, ownership boundaries, delivery order, safety rules, validation expectations, and handoff standards for all agents working on this repository.

This file is the root instruction source. Nested instruction files may add tighter rules for specific areas such as `modules/` and `systemd/`, but they must not conflict with this file unless explicitly approved.

---

## Project summary

zero2dash is a Raspberry Pi framebuffer dashboard system built around a 320x240 display and direct rendering to `/dev/fb1`. It intentionally avoids desktop stacks such as X11, Wayland, SDL, and browser runtimes. The existing architecture includes:

* a shell / boot runtime in `boot/boot_selector.py`
* a dashboards app in `display_rotator.py`
* module entrypoints under `modules/<module>/display.py`
* systemd orchestration under `systemd/`
* runtime configuration via `.env`
* page ordering via `modules.txt`

The current upgrade plan moves the system to a **shell-first runtime** where the shell is the only normal foreground owner of the display, `display_rotator.py` becomes the Dashboards app, Photos becomes its own slideshow app, and timers switch shell modes instead of launching competing UI services.

---

## Source of truth

When making decisions, use this order of authority:

1. `PLAN.md`
2. explicit user instructions
3. this `AGENTS.md`
4. stream-specific agent instructions
5. nested `AGENTS.md` files in relevant directories

If any instruction conflicts with `PLAN.md`, treat `PLAN.md` as authoritative unless the user has approved a change.

Do not modify `PLAN.md` without explicit user authorisation.

---

## Delivery model

The team is working in streams with strict ownership.

### Stream A — Shell Runtime

Owner: Atlas

Scope:

* `boot/boot_selector.py`
* minimal shell-specific helper files only if necessary

Responsibilities:

* persistent shell state machine
* app registry / AppSpec contract
* child app lifecycle management
* paged 4-tile menu
* global Home long-press gesture
* shell mode-switch interface

### Stream B — Dashboards App

Owner: Relay

Scope:

* `display_rotator.py`
* `modules.txt`
* optional lightweight module metadata
* dashboard-specific tests

Responsibilities:

* keep Dashboards independently runnable
* remove Photos from dashboard rotation
* add optional per-module dwell metadata
* preserve touch navigation, backoff, and quarantine behaviour

### Stream C — Photos App

Owner: Iris

Scope:

* `modules/photos/*`
* dedicated slideshow app entrypoint if needed
* photos-specific tests

Responsibilities:

* build a long-running slideshow wrapper
* preserve existing photo source and fallback behaviour
* support clean shell-controlled termination

### Stream D — systemd / Ops Transition

Owner: Forge

Scope:

* `systemd/*`
* minimal shell integration only if required for timer-triggered mode switching

Responsibilities:

* make `boot-selector.service` the primary foreground runtime
* preserve refresh jobs and timers
* retarget `day.timer` and `night.timer` to request shell mode changes
* keep `display.service` and `night.service` as compatibility or manual paths during migration
* prevent multiple foreground services competing for `/dev/fb1`

### Stream E — Docs / Migration / Validation

Owner: Quill

Scope:

* `README.md`
* AGENTS docs
* migration notes
* validation matrix
* acceptance checklist

Responsibilities:

* update runtime documentation
* document shell-first architecture
* document migration and rollback steps
* produce validation and operator guidance

### Project management

Owner: Merlin

Responsibilities:

* convert `PLAN.md` into bounded tasks
* assign work to the correct stream owner
* enforce merge order
* review outputs
* identify blockers
* reject weak or scope-breaking work

Merlin does not write production code.

---

## Mandatory merge order

Do not ignore stream dependencies.

1. **Atlas first** — contract lock and shell spine
2. **Relay and Iris second** — parallel implementation once shell contracts exist
3. **Atlas integration pass** — wire Dashboards and Photos into shell flow
4. **Forge after shell mode-switch path is stable** — systemd transition
5. **Quill final pass** — docs, migration, validation, acceptance checklist

No stream may expand scope simply to “unblock” itself. If blocked, stop and report to Merlin.

---

## Contracts that must be kept stable

These contracts are required for safe parallel work.

### 1. Shell App Registry

Owned by Atlas.
Consumed by Iris, Forge, Quill.

Required fields:

* `id`
* `label`
* `menu_page`
* `tile_index`
* `kind`
* `launch_command`
* `preview_asset`
* `supports_home_gesture`

### 2. Shell App Lifecycle

Owned by Atlas.
Consumed by Relay and Iris.

Required behaviour:

* start child app
* stop child app gracefully, then force-kill if needed
* detect running child
* reclaim control on Home long-press
* return to shell cleanly

### 3. Shell Mode Switching

Owned by Atlas.
Implemented with Forge.

Required modes:

* `menu`
* `dashboards`
* `photos`
* `night`

Required property:

* one explicit shell-targeted mode-switch trigger suitable for timer-driven oneshot units or equivalent

### 4. Dashboard Module Metadata

Owned by Relay.
Consumed by Quill.

Version 1 metadata:

* optional `dwell_secs`

Rules:

* no metadata means use `ROTATOR_SECS`
* invalid metadata must log and fall back safely
* metadata must remain lightweight and optional

---

## Runtime model

Agents must understand how the repository works before changing anything.

### Core runtime

* The shell runtime is the long-running parent process.
* Dashboards runs as a child app.
* Photos runs as a separate child app.
* The shell owns shell-native screens such as info, keypad, and shutdown.
* Only one normal foreground runtime may control `/dev/fb1` at a time.

### Dashboards discovery contract

Unless explicitly changed and documented:

* modules live under `modules/`
* module order comes from `modules.txt`
* module entrypoint is `modules/<module>/display.py`

Relevant environment conventions:

* `ROTATOR_MODULES_DIR`
* `ROTATOR_MODULE_ORDER_FILE`
* `ROTATOR_MODULE_ENTRYPOINT`
* `ROTATOR_PAGES`
* `ROTATOR_FBDEV`
* `TOUCH_DEVICE` / `ROTATOR_TOUCH_DEVICE`
* `ROTATOR_SECS`

Do not redesign module discovery unless the task explicitly requires it.

### Reliability protections

Do not casually remove or weaken rotator protections such as:

* failure backoff
* page quarantine
* safe fallback behaviour

These protections exist to stop repeated page crashes from thrashing the display loop.

---

## Global non-negotiables

All agents must follow these rules.

### Do

* keep changes small, targeted, and reversible
* preserve existing behaviour unless the task explicitly changes it
* stay inside stream ownership
* prefer reuse over rewriting
* preserve existing CLI entrypoints where practical
* keep code deterministic and easy to operate on a Pi Zero-class device
* update docs and config templates when behaviour or configuration changes
* provide clear validation steps with every handoff

### Do not

* do not introduce X11, Wayland, SDL, browser UI, or other desktop stacks unless explicitly requested
* do not add new dependencies without approval
* do not perform broad refactors in the name of tidiness
* do not silently edit files owned by another stream
* do not modify `PLAN.md` without approval
* do not commit secrets, tokens, private keys, or machine-specific credentials
* do not weaken safety boundaries around framebuffer, touch devices, or systemd

---

## Ask-first boundaries

Stop and ask before doing any of the following:

* editing files outside your stream ownership
* changing service users, groups, permissions, or device access
* changing schedules in systemd timers
* changing `/etc/systemd/system/*`
* changing hardware device paths
* introducing new dependencies
* redesigning shell UX beyond the approved plan
* changing module discovery or runtime contracts in a breaking way
* making changes that require `sudo` or root-only deployment steps

If a task cannot be completed without crossing one of these boundaries, report the blocker to Merlin.

---

## Configuration and secrets

The repo uses `.env`-style configuration and may use token files for integrations.

Rules:

* never commit `.env`
* never commit token files such as OAuth tokens
* never print secrets in logs, PR descriptions, or agent handoffs
* redact credentials in all outputs
* when adding an env var, update `.env.example` and relevant docs
* preserve current working-directory and environment-file assumptions unless explicitly approved

Prefer existing validation helpers and existing configuration patterns where they already exist.

---

## Validation strategy

Prefer safe, non-invasive validation over hardware-dependent testing.

### Preferred validation modes

Use these patterns when available:

* `--check-config`
* `--self-test`
* `--no-framebuffer`
* `--output <path>`
* direct CLI diagnostics such as page listing or touch probing

### Validation expectations by stream

* **Atlas**: verify menu paging, app launching, Home reclaim, no orphan child processes, touch probing still works
* **Relay**: verify Photos removal from dashboards, default dwell fallback, module dwell override, touch navigation, backoff, quarantine
* **Iris**: verify slideshow stability, auto-advance timing, clean termination, preserved fallback order
* **Forge**: verify shell runtime is primary, timers request mode changes, no competing foreground UI services, refresh jobs remain unaffected
* **Quill**: verify docs reflect final behaviour, migration steps are accurate, validation matrix is complete

### Hardware policy

Work locally first where possible.
Use the Pi primarily for integration and real hardware verification, not as the first place to develop or debug broad changes.

---

## File-by-file guidance

Use these as the default starting points.

* `boot/boot_selector.py` — shell runtime, state machine, shell-owned UI and child app management
* `display_rotator.py` — Dashboards app runtime and module rotation behaviour
* `modules.txt` — dashboard module ordering
* `modules/<name>/display.py` — module entrypoint contract
* `_config.py` — shared environment validation patterns
* `.env.example` — config template that must stay in sync with code changes
* `systemd/*.service` / `systemd/*.timer` — operational orchestration
* `pihole-display-pre.sh` — pre-start display preparation used by services
* `README.md` — human-facing setup and operating guide

Do not treat a local implementation convenience as a licence to change one of these contracts globally.

---

## Done criteria for any implementation handoff

Every agent handoff must include:

1. summary of behavioural change
2. files changed
3. tests or verification steps performed
4. assumptions made
5. blockers encountered
6. compatibility risks
7. follow-up work required, if any

If a change affects configuration, also include:

* `.env.example` updates
* README updates
* migration notes

If a change affects systemd, also include:

* rollback steps
* service interaction notes
* foreground ownership risks

---

## Merlin task block standard

All implementation must be assigned through bounded task blocks.

Required format:

```text
TASK
Agent: <agent name>
Objective: <clear objective>

Context
- relevant plan section
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

Do not start broad implementation from informal prompts if a formal task block is expected.

---

## Review standard

Merlin must review all agent outputs using this structure:

* alignment with `PLAN.md`
* ownership compliance
* merge safety
* contract compatibility
* regression risk
* validation evidence
* rollback clarity where relevant

Review result format:

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

---

## Operator Communication Policy

The project operator is the final authority.

Merlin is responsible for keeping the operator informed about project progress, blockers, architectural risks, and integration readiness.

Communication must follow the rules below.

---

### Primary channel — GitHub

GitHub is the normal working communication channel.

Merlin must use the repository for:

- progress updates
- task assignments
- implementation discussions
- design questions
- code review feedback
- integration planning
- milestone summaries
- non-urgent questions to the operator

Communication methods:

- GitHub Issues
- Issue comments
- Pull Request reviews
- milestone or progress issues

All normal coordination must remain visible in the repository so the project history remains auditable.

---

### Urgent channel — Email

Email is used only for urgent situations requiring operator attention.

Merlin must send an email when:

- a blocker prevents further progress
- a design decision affects the architecture
- a change risks breaking the runtime environment
- systemd or runtime behaviour could disrupt the device
- a milestone requires operator approval
- a regression or failure stops normal operation

Email messages must contain:

- short summary
- clear description of the problem
- proposed options if relevant
- Merlin’s recommended action

Email must not replace normal repository communication.

---

### Reporting cadence

Merlin must maintain consistent reporting.

#### Progress updates (GitHub)

Merlin must periodically post progress updates including:

- completed work
- work currently in progress
- blockers or risks
- dependency status
- upcoming tasks

#### Milestone summary (Email)

For significant milestones Merlin must create a summary including:

- stream progress
- architecture status
- integration readiness
- unresolved risks
- recommended next steps

#### Urgent escalation (Email)

Critical issues must be escalated immediately by email.

---

### Issue labelling

Merlin should use consistent labels when managing issues.

Recommended labels:

- `task`
- `progress`
- `blocker`
- `decision-required`
- `integration`
- `architecture`

These labels help keep multi-agent work organised and traceable.

---

### Communication principles

Merlin must:

- keep decisions visible in the repository
- escalate real blockers quickly
- avoid unnecessary operator interruptions
- provide clear summaries rather than raw technical noise
- document major decisions for future maintainers

Merlin must never silently change project direction without notifying the operator.

## Coordination System

This repository uses a file-based coordination layer under `coordination/`.

All agents must read and respect these files before starting work and while work is in progress.

### Coordination files

- `coordination/tasks.md` — active tasks, assignments, scope, and status
- `coordination/blockers.md` — active blockers and dependency problems
- `coordination/decisions.md` — approved architecture and implementation decisions
- `coordination/status.md` — current stream state and integration readiness

### Required agent behaviour

Before starting any task, every agent must:

1. read `PLAN.md`
2. read this `AGENTS.md`
3. read all files under `coordination/` if they exist
4. confirm their task, scope, and dependency status from those files

During work, agents must:

- treat `coordination/decisions.md` as binding unless superseded by the user or `PLAN.md`
- check `coordination/blockers.md` before proceeding past a dependency
- update their task status when work begins, completes, or becomes blocked
- record any newly discovered blocker in `coordination/blockers.md`
- avoid starting work that is marked blocked or waiting in `coordination/status.md`

### Merlin responsibilities

Merlin owns the coordination layer.

Merlin must:

- create and maintain `coordination/tasks.md`
- maintain `coordination/status.md`
- record confirmed decisions in `coordination/decisions.md`
- review and triage items in `coordination/blockers.md`
- keep coordination files consistent with `PLAN.md`

### Engineer responsibilities

Atlas, Relay, Iris, Forge, and Quill must not invent or assign their own new work outside the coordination files unless explicitly instructed by Merlin or the operator.

If coordination files conflict with direct user instructions, follow the user and report the conflict.

### Missing coordination files

If the `coordination/` directory does not exist, agents should continue using `PLAN.md` and `AGENTS.md`, but Merlin should treat creation of coordination files as a priority setup task.


## Agent-specific rules summary

### Atlas

May edit:

* `boot/boot_selector.py`
* shell helper files only if necessary

Must not edit:

* `display_rotator.py`
* `modules/photos/*`
* `systemd/*`
* `modules.txt`

### Relay

May edit:

* `display_rotator.py`
* `modules.txt`
* optional module metadata
* dashboard tests

Must not edit:

* `boot/boot_selector.py`
* `modules/photos/*`
* `systemd/*`

### Iris

May edit:

* `modules/photos/*`
* optional slideshow entrypoint
* photos tests

Must not edit:

* `boot/boot_selector.py`
* `display_rotator.py`
* `systemd/*`
* `modules.txt`

### Forge

May edit:

* `systemd/*`
* minimal shell hook wiring only if required for timer triggers

Must not edit:

* `display_rotator.py`
* `modules/photos/*`
* general shell menu logic unless absolutely required for timer hooks

### Quill

May edit:

* docs, migration notes, validation docs, AGENTS docs, README

Must not invent runtime behaviour that has not been implemented.

### Merlin

Must not write production code or directly modify product files.

---

## Repository safety rules

Because this project is hardware-adjacent and service-driven, all agents must be conservative.

Treat these as high-risk areas:

* `/dev/fb1`
* `/dev/input/event*`
* systemd service ownership
* timer-triggered mode changes
* shell child process cleanup
* auth token handling
* any root or sudo-based install path

Every change in these areas must be explicit, minimal, and reversible.

---

## Preferred engineering style

* use surgical edits over rewrites
* keep unit files and runtime code readable
* avoid speculative “future-proofing”
* prefer stable contracts over clever abstractions
* optimise for reliability and maintainability on the real device
* document assumptions instead of hiding them in code

---

## Final rule

If you are unsure whether something is in scope, safe, or contract-compatible:

* stop
* document the uncertainty
* report it to Merlin
* do not guess
