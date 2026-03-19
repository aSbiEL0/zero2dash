# Tasks

Live status: OPENED on 2026-03-19 for post-merge shell stabilization.

Rules:
- Mouser assigns and re-sequences tasks.
- Engineers update status for their own stream.
- Keep tasks bounded, merge-safe, and reversible.
- Do not expand scope beyond `PLAN.md` without an operator decision.

---

## Active Tasks

TASK ID: R-021
Agent: Mouser
Status: COMPLETE

Objective:
Replace the stale shell-owned-app planning layer with a clean post-merge stabilization control plane.

Allowed files:
- `PLAN.md`
- `AGENTS.md`
- `boot/AGENTS.md`
- `docs/plans/*`
- `coordination/*`
- `.codex/agents/*`

Forbidden files:
- runtime code
- `systemd/*`

Deliverables:
- active `PLAN.md`
- new stabilization plan
- aligned root/nested AGENTS files
- refreshed coordination state
- aligned agent `.toml` specs

Acceptance criteria:
- old shell-owned-app planning is clearly superseded
- one active stabilization story remains
- first-wave roles and reserve roles are explicit
- coordination starts from a fresh, relevant baseline

Dependencies:
- none

---

TASK ID: R-022
Agent: Pathfinder
Status: OPEN

Objective:
Verify the current Themes/touch/Settings reality before shell code edits begin.

Allowed files:
- `boot/boot_selector.py`
- `themes/*`
- `tests/test_boot_selector.py`
- `coordination/status.md`
- `coordination/decisions.md`
- `coordination/blockers.md`

Forbidden files:
- runtime code edits
- `systemd/*`

Deliverables:
- verified theme-order mismatch notes
- verified lower-row touch-zone notes
- verified Settings render seam notes
- blocker note if recalibration-first assumptions look unsafe

Acceptance criteria:
- repo evidence distinguishes real shell issues from stale assumptions
- theme/touch decisions are backed by actual code/assets
- Mouser can hand implementation to Switchboard without guessing

Dependencies:
- `R-021`

---

TASK ID: R-023
Agent: Switchboard
Status: OPEN

Objective:
Fix Themes screen behavior so visible buttons map correctly and hidden lower-row zones are inactive.

Allowed files:
- `boot/boot_selector.py`
- `tests/test_boot_selector.py`
- `coordination/status.md`

Forbidden files:
- `display_rotator.py`
- `modules/*`
- `systemd/*`

Deliverables:
- explicit top-row theme order
- inactive lower-row theme zones
- focused selector regressions

Acceptance criteria:
- Carbon Black maps to `default`
- Brushed Steele maps to `steele`
- Comic Book maps to `comic`
- lower-row taps do nothing with current art

Dependencies:
- `R-022`

---

TASK ID: R-024
Agent: Switchboard
Status: OPEN

Objective:
Reformat Settings text rendering without changing the underlying summary content providers.

Allowed files:
- `boot/boot_selector.py`
- `tests/test_boot_selector.py`
- `coordination/status.md`

Forbidden files:
- `display_rotator.py`
- `modules/*`
- `systemd/*`

Deliverables:
- centered title/body composition shifted 10px left
- more spacious layout
- truncation/ellipsis behavior instead of dense wrapping
- focused rendering regressions

Acceptance criteria:
- Network, Pi Stats, and Logs remain the same data sources
- text becomes readable on `stats.png`
- no overflow or uncontrolled wrapping remains

Dependencies:
- `R-023`

---

TASK ID: R-025
Agent: Sentinel
Status: OPEN

Objective:
Harden selector regressions around Themes mapping, lower-row inactivity, and Settings rendering.

Allowed files:
- `tests/test_boot_selector.py`
- `coordination/status.md`
- `coordination/blockers.md`

Forbidden files:
- runtime code except narrow test-linked seams approved by Mouser
- `systemd/*`

Deliverables:
- shell regression coverage
- sign-off notes for code-side checks
- blocker note if tests expose a deeper touch issue

Acceptance criteria:
- tests protect explicit theme order
- tests protect lower-row inactivity
- tests protect Settings formatting constraints

Dependencies:
- `R-024`

---

TASK ID: R-026
Agent: Curator
Status: OPEN

Objective:
Refresh operator-facing docs after shell behavior and regressions are stabilized.

Allowed files:
- `README.md`
- `PLAN.md`
- `AGENTS.md`
- `boot/AGENTS.md`
- `coordination/status.md`

Forbidden files:
- runtime code
- `systemd/*`

Deliverables:
- aligned README notes
- validation guidance for recalibration-first touch sign-off
- documentation of current Themes behavior

Acceptance criteria:
- docs match actual landed shell behavior
- active plan/source-of-truth references stay consistent
- NASA is explicitly out of scope in current docs

Dependencies:
- `R-025`

---

TASK ID: R-027
Agent: Framekeeper
Status: HOLD

Objective:
Stand by for escalation only if recalibrated menu touches still misfire and the blocker is no longer explainable by shell mapping or stale calibration.

Allowed files:
- `boot/boot_selector.py`
- `touch_calibration.py`
- framebuffer-adjacent helpers if explicitly approved
- `coordination/*`

Forbidden files:
- broad shell redesign
- `systemd/*`
- unrelated module trees

Deliverables:
- targeted diagnosis
- bounded fix only if needed

Acceptance criteria:
- reserve role is used only when calibration-first validation proves insufficient

Dependencies:
- `R-025`
