# Tasks

Live status: OPENED on 2026-03-19 for shell-owned app stabilization.

Rules:
- Mouser assigns and re-sequences tasks.
- Engineers update status for their own stream.
- Keep tasks bounded, merge-safe, and reversible.
- Do not expand scope beyond `PLAN.md` without an operator decision.

---

## Active Tasks

TASK ID: R-015
Agent: Mouser
Status: COMPLETE

Objective:
Replace the archived planning state with a live plan for Photos, Settings, Themes, and dashboard-layout guidance.

Allowed files:
- `PLAN.md`
- `docs/plans/*`
- `coordination/*`

Forbidden files:
- runtime code
- `systemd/*`

Deliverables:
- active `PLAN.md`
- detailed execution plan
- reopened coordination files

Acceptance criteria:
- `PLAN.md` no longer points at the archived shell-repair slice
- the new plan names owners, dependencies, and merge order
- coordination reflects the live workstream

Dependencies:
- none

---

TASK ID: R-016
Agent: Pathfinder
Status: COMPLETE

Objective:
Verify the live asset, theme, and Photos touch contracts before implementation starts.

Allowed files:
- `themes/*`
- `boot/boot_selector.py`
- `modules/photos/*`
- `tests/test_boot_selector.py`
- `tests/test_photos.py`
- `coordination/status.md`
- `coordination/decisions.md`

Forbidden files:
- runtime code edits
- `systemd/*`

Deliverables:
- verified theme inventory
- verified shell asset contract
- verified Photos touch seam notes

Acceptance criteria:
- coordination records only verified facts
- theme count and path assumptions are explicit
- Photos input/exit seam is documented for implementation agents

Dependencies:
- `R-015`

---

TASK ID: R-017
Agent: Photos Worker
Status: OPEN

Objective:
Implement child-owned dashboard-parity touch behavior for Photos while preserving the existing child entrypoint and menu-request contracts.

Allowed files:
- `modules/photos/slideshow.py`
- `modules/photos/display.py`
- `tests/test_photos.py`
- `coordination/status.md`

Forbidden files:
- `boot/boot_selector.py`
- `display_rotator.py`
- `systemd/*`
- unrelated module trees

Deliverables:
- left/right/hold touch behavior in Photos
- menu-request exit path from the child runtime
- focused regression tests

Acceptance criteria:
- tap left selects previous photo
- tap right selects next photo
- hold requests menu exit
- shell-boundary changes remain in `R-018`

Dependencies:
- `R-016`

---

TASK ID: R-018
Agent: Switchboard
Status: OPEN

Objective:
Implement the shell-side Photos handoff, operator-summary Settings content, generated Themes mapping for up to 6 themes, and named shell layout knobs for status screens.

Allowed files:
- `boot/boot_selector.py`
- `tests/test_boot_selector.py`
- `coordination/status.md`

Forbidden files:
- `display_rotator.py`
- `systemd/*`
- unrelated module trees

Deliverables:
- shell-side Photos ownership handoff
- real Settings summaries
- generated theme picker mapping
- named shell status layout constants

Acceptance criteria:
- Photos no longer leaves the parent shell consuming the same gesture path while the child is active
- Network, Pi Stats, and Logs screens render fallback-safe summaries
- theme picker derives touch mapping from discovered themes
- up to 6 themes fit on one screen without paging
- shell status text layout is adjustable via named constants

Dependencies:
- `R-016`

---

TASK ID: R-019
Agent: Sentinel
Status: OPEN

Objective:
Add regression coverage for Photos touch behavior, Settings summaries, and theme-grid mapping.

Allowed files:
- `tests/test_boot_selector.py`
- `tests/test_photos.py`
- `coordination/status.md`

Forbidden files:
- runtime code except approved narrow seams
- `systemd/*`

Deliverables:
- focused hardware-free regressions
- coverage for fallback behavior and deterministic theme mapping

Acceptance criteria:
- test suite covers Photos left/right/hold behavior
- test suite covers non-empty Settings summaries with fallback states
- test suite covers 1..6 theme mapping and in-place apply behavior

Dependencies:
- `R-017`
- `R-018`

---

TASK ID: R-020
Agent: Curator
Status: OPEN

Objective:
Update operator-facing docs after runtime behavior stabilizes.

Allowed files:
- `README.md`
- `coordination/status.md`

Forbidden files:
- runtime code
- `systemd/*`

Deliverables:
- margin tuning documentation
- Photos touch contract documentation
- Settings and Themes behavior notes

Acceptance criteria:
- docs name the real files and knobs
- docs match landed runtime behavior

Dependencies:
- `R-019`

