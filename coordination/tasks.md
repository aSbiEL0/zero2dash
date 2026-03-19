# Tasks

This file tracks active work assignments for the shell repair and asset-backed menu rebuild.
`PLAN.md` is the only execution source of truth. This file is a progress ledger for the current run only.

Rules:
- Mouser assigns and re-sequences tasks.
- Engineers update status for their own stream.
- Keep tasks bounded, merge-safe, and reversible.
- Do not expand scope beyond `PLAN.md` without an operator decision.
- Archive entries from previous agent teams are historical context only and are not authoritative.

---

## Task Template

TASK ID: R-XXX
Agent:
Status: OPEN | IN_PROGRESS | BLOCKED | COMPLETE

Objective:
<clear objective>

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

TASK ID: R-014
Agent: Mouser
Status: IN_PROGRESS

Objective:
Repair the remaining Pi interaction defects by fixing touch calibration, Dashboard routing, child touch ownership, and ADS7846 event handling across the shell and child apps.

Allowed files:
- `boot/boot_selector.py`
- `display_rotator.py`
- `rotator/*`
- `modules/blackout/blackout.py`
- `touch_calibration.py`
- `tests/*`
- `coordination/*`

Forbidden files:
- `systemd/*`
- unrelated module trees

Deliverables:
- corrected `main_menu_1` routing into `dashboards_menu`
- parent/child touch ownership contract for dashboards and night
- shared ADS7846-compatible touch handling in shell, rotator, and blackout
- reusable touch calibration flow and regression coverage

Acceptance criteria:
- Dashboards button opens `dashboards_menu` instead of freezing touch
- Dashboards and Night can return to menu under shell ownership rules
- Photos can still be exited by shell hold-to-menu
- keypad confirm/cancel mapping matches the themed asset after calibrated mapping
- touch calibration can be diagnosed and regenerated on-device without editing code

Dependencies:
- `R-010`
- `R-011`
- `R-012`

---

TASK ID: R-013
Agent: Curator
Status: COMPLETE

Objective:
Update repo-facing documentation and the GitHub wiki so they reflect the now-landed shell repair and asset-backed menu rebuild accurately.

Allowed files:
- `README.md`
- docs/wiki working files created for the update
- `coordination/*`

Forbidden files:
- runtime code
- tests
- `systemd/*`

Deliverables:
- refreshed repo documentation
- prepared GitHub wiki updates
- publish-ready wiki repo update once Pi smoke validation confirms runtime behavior
- concise operator-facing summary of doc changes

Acceptance criteria:
- repo docs describe the real current shell, rotator, and test baseline
- wiki content matches `PLAN.md`-aligned runtime behavior
- remaining Pi-only validation gaps are documented explicitly
- remote publication waits until Pi smoke confirmation closes the last validation gate

Dependencies:
- `R-009`
- `R-010`
- `R-011`
- `R-012`

---

TASK ID: R-009
Agent: Mouser
Status: COMPLETE

Objective:
Re-lock the repo control plane to `PLAN.md`, replace stale rebuild coordination state, sequence the current work, and manage merge order across Rotor, Switchboard, and Sentinel.

Allowed files:
- `coordination/*`

Forbidden files:
- runtime code
- `systemd/*`

Deliverables:
- updated coordination files
- dependency-ordered execution tracking
- merge gate decisions

Acceptance criteria:
- `PLAN.md` is recorded as the active source of truth
- active blockers and assignments reflect the real repo state
- merge order is explicit before cross-stream integration

Dependencies:
- none

---

TASK ID: R-010
Agent: Rotor
Status: COMPLETE

Objective:
Repair the broken dashboards runtime by resolving committed merge-conflict residue in the rotator path while preserving current runtime contracts, including backoff/quarantine behavior and long-press return to the shell.

Allowed files:
- `display_rotator.py`
- `display_layout.py`
- `modules/trams/display.py`
- `rotator/*`
- `tests/test_display_rotator.py`
- `coordination/*`

Forbidden files:
- `boot/*`
- `systemd/*`
- unrelated module trees

Deliverables:
- conflict-free runtime files
- restored rotator touch contract for `MAIN_MENU`
- bounded regression coverage for repaired rotator behavior

Validation:
- `C:\Users\Default.DESKTOP-MR88P09\AppData\Local\Programs\Python\Python313\python.exe -m py_compile display_rotator.py display_layout.py modules\trams\display.py rotator\touch.py tests\test_display_rotator.py`
- `C:\Users\Default.DESKTOP-MR88P09\AppData\Local\Programs\Python\Python313\python.exe -m unittest tests.test_display_rotator`
- `C:\Users\Default.DESKTOP-MR88P09\AppData\Local\Programs\Python\Python313\python.exe modules\trams\display.py --self-test`

Acceptance criteria:
- no merge markers remain in the allowed files
- `display_rotator.py` imports cleanly again
- long-press return path is preserved
- non-zero early exits still feed backoff/quarantine accounting

Dependencies:
- `R-009`

---

TASK ID: R-011
Agent: Switchboard
Status: COMPLETE

Objective:
Replace the old paged shell selector with the theme-backed screen-state shell described in `PLAN.md` while preserving shell ownership, mode switching, and child lifecycle contracts.

Allowed files:
- `boot/boot_selector.py`
- shell-local helper files if created under `boot/`
- `coordination/*`

Forbidden files:
- `display_rotator.py`
- `systemd/*`
- `modules/*`

Deliverables:
- theme discovery and validation
- theme-backed routing/state model
- immediate theme persistence and in-session root-page restore

Acceptance criteria:
- shell uses real assets from `themes/*`
- `menu`, `dashboards`, `photos`, and `night` mode requests still work
- old generic selector assets are no longer required for runtime routing
- NASA ISS remains a shell-owned placeholder

Dependencies:
- `R-009`
- `R-010`

---

TASK ID: R-012
Agent: Sentinel
Status: COMPLETE

Objective:
Add regression coverage for the repaired rotator path and the rebuilt selector/router so the new shell and dashboard contracts stop drifting silently.

Allowed files:
- `tests/*`
- `coordination/*`

Forbidden files:
- runtime code except narrow test seams approved by Mouser
- `systemd/*`

Deliverables:
- rotator regression tests
- selector/router/theme tests
- asset validation assertions

Acceptance criteria:
- tests cover `MAIN_MENU`, screen toggle, failure reset, and early-exit failure handling
- tests cover theme discovery, root-page strip switching, themed routing, credits/keypad flows, and shared `stats.png` behavior
- tests run without Pi hardware

Dependencies:
- `R-010`
- `R-011`

---

## Archive Note

- Previous-team task records are archive material only.
- They do not define scope, contracts, or acceptance criteria for this run.
