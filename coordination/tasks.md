# Tasks

Live status: RESET on 2026-03-28 for themes, right-side back stripe, and Settings layout stabilization.

Rules:
- Mouser assigns and re-sequences tasks.
- Keep tasks bounded, merge-safe, and reversible.
- Progress must match `PLAN.md`.
- Do not reopen NASA or Photos scope without an explicit operator decision.

---

## Active Tasks

TASK ID: S-001
Agent: Mouser
Status: COMPLETE

Objective:
Reset the control plane to the active segmented shell slice and remove stale NASA/Photos execution drift.

Allowed files:
- `PLAN.md`
- `AGENTS.md`
- `coordination/*`

Forbidden files:
- runtime code
- `systemd/*`

Deliverables:
- segmented active `PLAN.md`
- repo-level `AGENTS.md` aligned to the active slice
- coordination files reset to current work only

Acceptance criteria:
- active scope is Themes, right-side back stripe, and Settings layout
- NASA is deferred
- Photos is out of active implementation scope

Dependencies:
- none

---

TASK ID: S-002
Agent: Pathfinder
Status: OPEN

Objective:
Verify the remaining Themes contract on the device and in the repo before final selector changes proceed.

Allowed files:
- `boot/boot_selector.py`
- `themes/*`
- `tests/test_boot_selector.py`
- `coordination/status.md`
- `coordination/decisions.md`

Forbidden files:
- runtime code edits
- `systemd/*`

Deliverables:
- verified live theme inventory
- verified current theme target mapping notes
- confirmed `themes.png` deployment follow-up status
- note on whether regression source files need to be created before coverage can be updated

Acceptance criteria:
- device theme inventory is explicitly recorded
- any remaining mismatch between `THEME_BUTTON_ORDER` and actual theme ids is described concretely
- the plan states whether a new `themes.png` upload is still pending

Dependencies:
- `S-001`

---

TASK ID: S-003
Agent: Switchboard
Status: OPEN

Objective:
Finish shell-side Themes behavior and move the back stripe to the right-hand side.

Allowed files:
- `boot/boot_selector.py`
- `tests/test_boot_selector.py`
- `coordination/status.md`

Forbidden files:
- `display_rotator.py`
- `systemd/*`
- unrelated module trees

Deliverables:
- final Themes routing fixes
- right-side back stripe
- focused regression coverage for touched shell routing if test sources exist, otherwise explicit note that new test sources must be created

Acceptance criteria:
- visible Themes targets map to the intended themes
- the shell back stripe is right-sided on affected shell screens
- no unrelated shell routing regresses in hardware-free checks

Dependencies:
- `S-002`

---

TASK ID: S-004
Agent: Switchboard
Status: OPEN

Objective:
Correct Settings text rendering and make manual code-side layout tuning obvious.

Allowed files:
- `boot/boot_selector.py`
- `tests/test_boot_selector.py`
- `coordination/status.md`

Forbidden files:
- `display_rotator.py`
- `systemd/*`
- UI/editor controls for layout tuning

Deliverables:
- corrected Settings text layout
- clearly labeled code constants for x, y, area, and font tuning
- a short code comment telling the operator what to edit

Acceptance criteria:
- Settings text renders acceptably
- tuning values are easy to find in code, including font choice or path and font size
- no layout editor UI is introduced

Dependencies:
- `S-003`

---

TASK ID: S-005
Agent: Sentinel
Status: OPEN

Objective:
Validate the remaining shell slice and record any device-only follow-up.

Allowed files:
- `tests/test_boot_selector.py`
- `coordination/status.md`
- `coordination/blockers.md`
- `README.md`

Forbidden files:
- broad runtime refactors
- `systemd/*`

Deliverables:
- focused validation notes for Themes, back stripe, and Settings layout
- explicit record of any pending on-device `themes.png` upload
- final segment status updates

Acceptance criteria:
- local and/or device validation evidence exists for each active segment
- unresolved device-only work is recorded plainly
- progress tracking matches actual state

Dependencies:
- `S-004`
