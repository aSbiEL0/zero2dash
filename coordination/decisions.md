# Architecture Decisions

Live status: OPENED on 2026-03-19.

Rules:
- Mouser or the operator records decisions.
- Recorded entries clarify execution within `PLAN.md`; they do not replace it.

---

DECISION ID: D-022
Status: ACTIVE

Topic:
Current active scope

Decision:
The active workstream is post-merge shell stabilization. The earlier shell-owned-app slice is superseded as the active planning story.

Reason:
The operator’s current goal is to clean up shell/menu regressions exposed after the bad NASA-branch merge, not to continue the previous Photos/Settings/Themes feature-oriented slice.

Implications:
- NASA app work is out of scope
- planning, coordination, and AGENTS files must point at one fresh active slice
- old coordination context remains historical only

Supersedes:
- `D-015`
- `D-016`
- `D-017`
- `D-018`
- `D-019`
- `D-020`
- `D-021`

---

DECISION ID: D-023
Status: ACTIVE

Topic:
Themes screen contract

Decision:
The current Themes screen must follow the visible top-row order `default`, `steele`, `comic`, and all lower-row touch zones are inactive until future visible buttons/assets explicitly restore extra slots.

Reason:
The operator confirmed the visible art order and explicitly stated that the lower three theme buttons were removed from the current design.

Implications:
- shell code must not derive current visible order from alphabetical sorting
- hidden live lower-row mapping is a bug in the current slice
- future extra-theme support must be reintroduced explicitly, not left half-live

Supersedes:
- generated 1..6 active Themes behavior as the current active contract

---

DECISION ID: D-024
Status: ACTIVE

Topic:
Touch stabilization strategy

Decision:
Touch stabilization for this slice is calibration-first. The current `--probe-touch` and `--calibrate-touch` workflow remains the approved path, and shell touch logic should not be changed unless recalibrated on-device checks still miss intended menu zones.

Reason:
The operator wants recalibration rather than speculative touch-code changes and asked specifically about on-device stylus calibration support.

Implications:
- docs and validation must emphasize the operator calibration workflow
- code churn in touch math is not the default fix
- a visual calibration UI is future work only

Supersedes:
None

---

DECISION ID: D-025
Status: ACTIVE

Topic:
Settings rendering scope

Decision:
Settings remains in scope, but only as a text-rendering task. Current Network, Pi Stats, and Logs summary providers stay unchanged; only the composition, spacing, alignment, and truncation behavior may change.

Reason:
The operator confirmed the content is acceptable and only the way it is drawn must change.

Implications:
- Switchboard may rework the render layout
- shell data-gathering helpers are not to be reinvented in this slice
- tests should focus on rendering constraints rather than content-source changes

Supersedes:
operator-summary-content expansion as the current active focus

---

DECISION ID: D-026
Status: ACTIVE

Topic:
Execution team shape

Decision:
Use a standard specialized team:
- Mouser
- Pathfinder
- Switchboard
- Sentinel
- Curator

Framekeeper remains reserve-only. Rotor and Quartermaster remain out of the first wave unless scope expands.

Reason:
The operator asked for a specialized, efficient team that stays easy to manage and aligned with the goal.

Implications:
- first-wave execution stays narrow
- reserve roles need explicit justification before activation
- agent `.toml` files and AGENTS docs must reflect the same team shape

Supersedes:
None
