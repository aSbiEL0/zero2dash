# Tasks

Live status: RESET on 2026-03-28 for the NASA / ISS stabilization slice.

Rules:
- Mouser assigns and re-sequences tasks.
- Keep tasks bounded, merge-safe, and reversible.
- Progress must match `PLAN.md`.
- Preserve dashboards, Photos, and systemd/autostart unless the operator explicitly reopens them.

---

## Active Tasks

TASK ID: N-001
Agent: Mouser
Status: COMPLETE

Objective:
Reset the control plane from the completed shell slice to the active NASA slice.

Allowed files:
- `PLAN.md`
- `AGENTS.md`
- `coordination/*`
- `task_plan.md`

Forbidden files:
- runtime code
- `systemd/*`

Deliverables:
- active NASA `PLAN.md`
- repo-level `AGENTS.md` aligned to the NASA slice
- coordination files reset to NASA work only
- supporting delegation/task plan aligned to the new slice

Acceptance criteria:
- the active slice is NASA / ISS stabilization
- the completed shell slice is recorded as historical context, not active work
- the repo control plane matches current operator decisions

Dependencies:
- none

Completion notes:
- discovery and planning confirmed NASA is already partially implemented
- the active NASA plan now includes map asset correction, map calibration, flyover restoration, loading behavior, and code-only layout tuning

---

TASK ID: N-002
Agent: Pathfinder
Status: COMPLETE

Objective:
Establish the read-only baseline for current NASA runtime, shell wiring, API choices, rendering issues, and validation gaps.

Allowed files:
- `boot/boot_selector.py`
- `nasa-app/*`
- `README.md`
- `docs/wiki/Validation.md`
- `docs/nasa-app-review-2026-03-19.md`

Forbidden files:
- runtime edits
- `systemd/*`

Deliverables:
- verified NASA app entrypoints and shell route
- verified API/data model baseline
- verified rendering/layout defect list
- verified validation capabilities and gaps

Acceptance criteria:
- the repo’s real NASA state is described concretely
- active NASA work is based on inspected code, not stale docs

Dependencies:
- `N-001`

Completion notes:
- shell launch path is already present
- current NASA defects are now narrowed and concrete
- validation and API decisions are grounded in repo inspection and targeted source checks

---

TASK ID: N-003
Agent: Switchboard
Status: IN PROGRESS

Objective:
Implement the core NASA runtime fixes in `nasa-app/app.py`.

Allowed files:
- `nasa-app/app.py`
- `nasa-app/assets/*`

Forbidden files:
- `systemd/*`
- unrelated module trees
- broad shell refactors

Deliverables:
- correct map asset usage
- calibrated map plotting
- centralized operator-editable layout/font controls
- fixed crew-page rendering
- restored observer pass/flyover support
- faster startup path and loading screen behavior
- corrected `.env` lookup and stale-state handling

Acceptance criteria:
- map page uses the intended map assets and accurate plotting bounds
- crew pages no longer overlap
- the app shows a useful first frame quickly
- live or cached observer pass data is handled honestly
- operator-tunable layout settings are obvious in code

Dependencies:
- `N-002`

Progress notes:
- completed in this slice:
  - map assets now use `map.png` and `map-error.png`
  - map plotting now uses explicit configured overlay bounds
  - operator-editable layout/font controls are centralized in `nasa-app/app.py`
  - crew page now renders a visible `page/total` badge
  - repo-local `.env` precedence work was completed, then the now-dead observer scaffolding was removed pending the later pass/flyover slice
  - NASA asset-contract reset now aligns to the new `Downloads\\iss` pack:
    - map band reset to `x=0, y=40, width=320, height=160`
    - details and crew text boxes reset to the `260x180` guide contract at `x=30, y=30`
    - new guide images are now present under `nasa-app/assets/`
- still open in this task:
  - restored observer pass/flyover support
  - device confirmation for startup/loading behavior
  - stale-state tightening for the later pass/flyover runtime path

---

TASK ID: N-004
Agent: Sentinel
Status: IN PROGRESS

Objective:
Expand NASA validation to cover the real runtime branches and acceptance criteria.

Allowed files:
- `nasa-app/tests/test_nasa_app.py`
- optional NASA test fixtures under `nasa-app/tests/*`
- `coordination/status.md`
- `coordination/blockers.md`

Forbidden files:
- runtime feature edits beyond test support
- `systemd/*`

Deliverables:
- corrected NASA test harness
- branch coverage for live/fallback/offline and pass-cache behavior
- render checks for map, crew, loading, and error states
- explicit validation notes for automated vs device-only acceptance

Acceptance criteria:
- NASA tests cover more than smoke paths
- validation status is explicit and evidence-based
- missing fixture or device-only gaps are recorded honestly

Dependencies:
- `N-003`

Progress notes:
- completed in this slice:
  - duplicate module execution was removed from `nasa-app/tests/test_nasa_app.py`
  - deterministic offline-safe tests were added for map asset routing, display-name rendering path, crew badge labeling, and overflow page sequencing
  - map-band constant tests and anchor-point coverage were added for the new guide-derived geometry
  - details/crew guide-box constant tests were added for the new `260x180` layout contract
- still open in this task:
  - execution of automated checks in a working local Python environment
  - coverage for later pass/flyover runtime branches after those features land

---

TASK ID: N-005
Agent: Curator
Status: QUEUED

Objective:
Align repo-facing docs to the final NASA runtime and validation story after behavior is stable.

Allowed files:
- `README.md`
- `docs/wiki/Validation.md`
- `nasa-app/README.md`
- `coordination/status.md`

Forbidden files:
- runtime code
- `systemd/*`

Deliverables:
- updated NASA usage and validation docs
- final closeout notes matching the shipped implementation

Acceptance criteria:
- docs match the final NASA runtime behavior
- flyover/pass behavior and loading behavior are documented accurately
- validation commands are current

Dependencies:
- `N-004`

---

TASK ID: N-006
Agent: Framekeeper
Status: CONDITIONAL

Objective:
Support NASA asset correction only if existing NASA art proves insufficient.

Allowed files:
- `nasa-app/assets/*`

Forbidden files:
- runtime code
- shell/runtime files

Deliverables:
- corrected or replacement NASA visual assets only if needed

Acceptance criteria:
- no asset churn occurs unless runtime evidence shows the current art cannot support the agreed behavior

Dependencies:
- `N-003`
