# Tasks

This file tracks active work assignments for the remediation rebuild.

Rules:
- Only Merlin assigns new tasks.
- Engineers update status only.
- Keep tasks bounded and merge-safe.
- Do not expand scope to solve adjacent problems.

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

TASK ID: R-007  
Agent: Merlin  
Status: OPEN  

Objective:
Audit and normalize failure semantics so genuine runtime and refresh failures return non-zero consistently without weakening existing rotator backoff or quarantine protection.

Allowed files:
- `display_rotator.py`
- `modules/*`
- relevant tests
- `coordination/*`

Forbidden files:
- `boot/*`
- menu/UI redesign files
- unrelated assets

Deliverables:
- bounded task split for implementation agents
- current failure-semantics gap summary
- updated coordination state

Acceptance criteria:
- remaining failure-semantics work is explicitly scoped
- active gaps are identified before more feature work starts
- coordination files clearly separate completed rebuild slices from pending work

Dependencies:
- `R-001`
- `R-002`
- `R-003`
- `R-004`
- `R-005`

---

TASK ID: R-008  
Agent: Merlin  
Status: COMPLETE  

Objective:
Produce a concise current-state assessment of the software and the remaining areas that require Pi validation or technical review before the rebuild can be closed.

Allowed files:
- `coordination/status.md`
- `coordination/tasks.md`
- `rebuild-plan.md`

Forbidden files:
- runtime code
- `boot/*`
- `systemd/*`

Deliverables:
- current-state summary
- explicit review/watch list
- cleaned coordination references

Acceptance criteria:
- operator can see what is done, what is pending, and what needs checking next
- completed rebuild tasks are not mixed into the active queue

Dependencies:
- `R-007`

---

## Completed Tasks
TASK ID: R-000  
Agent: Merlin  
Status: COMPLETE  

Objective:
Reset the repo control plane around the remediation rebuild by replacing stale planning artifacts, cleaning live coordination files, and removing obvious transient clutter.

Allowed files:
- `rebuild-plan.md`
- `PLAN.md`
- `AGENTS.md`
- `coordination/*`
- `.gitignore`

Forbidden files:
- runtime code
- `systemd/*`
- `modules/*`
- tests

Deliverables:
- cleanup of planning and coordination artifacts
- updated repo-level instructions
- summary of changes and next tasks

Acceptance criteria:
- remediation plan is the active execution plan
- coordination files no longer reflect obsolete shell-split task state
- contaminated status transcript is replaced with a concise live status summary

Dependencies:
- none

TASK ID: R-001  
Agent: Relay  
Status: COMPLETE

Objective:
Continue decomposing `display_rotator.py` by extracting touch handling and screen-power control into internal rotator modules without changing the dashboards entrypoint contract.

Allowed files:
- `display_rotator.py`
- `rotator/*`
- `tests/test_display_rotator.py`

Forbidden files:
- `boot/*`
- `systemd/*`
- `modules/photos/*`
- non-rotator modules

Deliverables:
- implementation
- hardware-free validation results
- summary of compatibility impact

Acceptance criteria:
- touch logic no longer lives inline in the main rotator control path
- screen-power logic no longer lives inline in the main rotator control path
- `display_rotator.py` remains the supported dashboards entrypoint
- behavior remains compatible with existing dashboard launch and navigation flow

Dependencies:
- `616c169`

TASK ID: R-002  
Agent: Iris  
Status: COMPLETE

Objective:
Finish consolidating framebuffer and RGB565 handling by migrating remaining image-producing paths to `framebuffer.py` and removing duplicate conversion helpers.

Allowed files:
- `framebuffer.py`
- `modules/*`
- `tests/test_framebuffer.py`

Forbidden files:
- `boot/*`
- `systemd/*`
- `display_rotator.py`

Deliverables:
- implementation
- migration summary
- hardware-free validation results

Acceptance criteria:
- framebuffer write helpers are single-source for supported module paths
- duplicate RGB565 helpers are removed or reduced to compatibility wrappers only where required
- tests cover payload correctness and basic write-path validation

Dependencies:
- `616c169`

TASK ID: R-003  
Agent: Forge  
Status: COMPLETE

Objective:
Audit and harden service/runtime boundaries so refresh jobs do not depend on obsolete foreground-service assumptions, the service privilege model is explicit, and shell-facing integration follows the operator-selected stop/reclaim and request-file contracts.

Allowed files:
- `systemd/*`
- `README.md`

Forbidden files:
- `boot/*`
- `display_rotator.py`
- `modules/*`

Deliverables:
- implementation
- service interaction notes
- rollback notes

Acceptance criteria:
- refresh/update services do not depend on legacy foreground runtime assumptions
- normal foreground ownership remains explicit and non-competing
- service-user and device-access expectations are documented if changed

Dependencies:
- `R-001`
- `D-006`
- `D-007`

TASK ID: R-004  
Agent: Quill  
Status: COMPLETE

Objective:
Bring the docs in line with the remediation rebuild by documenting the shell-first baseline, extracted rotator architecture, framebuffer layer, validation strategy, and remaining risks.

Allowed files:
- `README.md`
- `AGENTS.md`
- `coordination/*`

Forbidden files:
- runtime code
- tests
- `systemd/*`

Deliverables:
- documentation updates
- validation matrix
- operator guidance

Acceptance criteria:
- docs describe the real current runtime and the remediation roadmap
- validation guidance matches reviewed code, not speculative behavior
- feature ideas remain clearly out of scope

Dependencies:
- `R-001`
- `R-002`
- `R-003`

TASK ID: R-005  
Agent: Atlas  
Status: COMPLETE  

Objective:
Lock down the shell app registry, lifecycle contract, and mode-switch interface so downstream streams can depend on stable Shell A contracts without regressing existing entrypoint behavior.

Allowed files:
- `boot/boot_selector.py`
- coordination/decisions.md

Forbidden files:
- `display_rotator.py`
- `modules/*`
- `systemd/*`

Deliverables:
- documented shell app registry schema (fields + validation) embedded near `AppSpec` or exported helper
- documented shell lifecycle expectations (start/stop, home gesture handling, child reclaim)
- documented shell mode-switch request interface (modes, storage path, fallback behavior)
- delta summary and suggested follow-up blockers/decisions if any contract gaps remain

Acceptance criteria:
- `AppSpec` fields match the required shell registry contract and there is code/comments to enforce them
- Lifecycle behavior is articulated in code/comments, and helper functions connect those behaviors to actual control flow without altering existing paths
- Mode-switch interface (request file semantics, `SHELL_MODES`, `handle_mode_request`) is fully described and exercised via existing logic; no new modes are introduced
- Atlas confirms no additional shell-owned apps beyond the known ones and documents how shell-owned vs child apps behave

Dependencies:
- `R-000`
- `D-006`
- `D-007`

