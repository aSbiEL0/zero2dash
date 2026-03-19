# Blockers

This file tracks issues preventing progress in the current run.
`PLAN.md` remains the only execution source of truth.

Rules:
- Any agent may log a blocker.
- Mouser decides resolution.
- Only Mouser may mark a blocker resolved.
- Archive blocker entries from previous teams are historical only.

---

## Blocker Template

BLOCKER ID: B-XXX
Raised by:
Status: OPEN | RESOLVED

Problem:
<clear description>

Impact:
- affected tasks
- affected agents

Possible cause:
<optional>

Suggested resolution:
<optional>

Notes:
<optional>

---

## Active Blockers

BLOCKER ID: B-001
Raised by: Mouser
Status: RESOLVED

Problem:
Committed merge-conflict markers currently break `display_rotator.py`, `display_layout.py`, and `modules/trams/display.py`.

Impact:
- blocks `R-010` validation
- blocks clean dashboards runtime execution
- increases risk for `R-011` because the shell rewrite depends on a working dashboards child

Possible cause:
An incomplete merge landed both legacy inline rotator code and extracted module code in the same files.

Suggested resolution:
Resolve the conflict residue in the Rotor stream first and preserve the extracted `rotator/*` architecture while restoring the `MAIN_MENU` long-press contract.

Notes:
Resolved by the Rotor stream on 2026-03-19. The files are conflict-free again and hardware-free verification passed.

No open software blockers remain in the current run. Remaining validation is hardware-side Pi verification.

BLOCKER ID: B-002
Raised by: Mouser
Status: RESOLVED

Problem:
The separate GitHub wiki repository had not been verified for remote publication.

Impact:
- previously blocked claiming remote wiki deployment readiness

Possible cause:
Initial Curator status was based on an outdated assumption about wiki remote access.

Suggested resolution:
None. The wiki remote was verified and cloned successfully.

Notes:
Remote publication is no longer blocked by access. It is intentionally held until Pi smoke confirmation finishes.
