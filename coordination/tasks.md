# Tasks

This file tracks active work assignments.

Rules:
- Only Merlin assigns new tasks.
- Engineers update **status** only.
- Do not change scope without Merlin approval.

---

## Task Template

TASK ID: T-XXX  
Agent:  
Status: OPEN | IN_PROGRESS | BLOCKED | COMPLETE  

Objective:
<clear objective>

Context:
- relevant section of PLAN.md
- dependency notes

Allowed files:
- path/to/file

Forbidden files:
- path/to/file

Deliverables:
- implementation
- validation steps
- summary of changes

Acceptance criteria:
- requirement
- requirement

Dependencies:
- task ID

---

## Active Tasks

TASK ID: T-001  
Agent: Atlas  
Status: OPEN  

Objective:
Lock the Phase 1 shell contracts and implement the shell runtime spine in `boot/boot_selector.py` without expanding into Dashboards, Photos, or systemd migration work.

Context:
- PLAN.md Phase 1: Contract Lock and Spine
- This is the first mergeable stream and must land before Relay, Iris, or Forge start contract-dependent implementation
- Current baseline still launches `display.service` / `night.service` directly and has no explicit AppSpec registry, shell state model, or shell mode-switch interface

Allowed files:
- boot/boot_selector.py
- boot/*
- coordination/blockers.md

Forbidden files:
- display_rotator.py
- modules.txt
- modules/photos/*
- systemd/*
- README.md
- PLAN.md

Deliverables:
- implementation of a shell-oriented runtime spine in `boot/boot_selector.py`
- explicit v1 shell contracts for app registry, child app lifecycle, and shell mode switching
- validation steps and results using safe local checks
- summary of changes, assumptions, blockers, compatibility risks, and follow-up work

Acceptance criteria:
- `boot/boot_selector.py` contains an explicit shell state model covering the planned shell-owned states
- the shell defines a concrete v1 app registry contract with required fields: `id`, `label`, `menu_page`, `tile_index`, `kind`, `launch_command`, `preview_asset`, `supports_home_gesture`
- child app lifecycle is abstracted behind shell-owned start/stop/status control rather than direct hard-coded UI service launches
- a concrete shell-targeted mode-switch interface exists for later timer integration, even if Stream D wiring is not implemented yet
- the change stays within Stream A ownership and does not modify Dashboards, Photos, systemd, or docs
- local validation evidence is provided without requiring hardware-only deployment steps

Dependencies:
- none
