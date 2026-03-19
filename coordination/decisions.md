# Architecture Decisions

Live status: OPENED on 2026-03-19.

Rules:
- Mouser or the operator records decisions.
- Recorded entries clarify execution within `PLAN.md`; they do not replace it.

---

DECISION ID: D-015
Status: ACTIVE

Topic:
Current app stabilization scope

Decision:
Treat Photos, Settings, and Themes as the active remediation stream. Dashboard is not in a rebuild stream and only receives narrow layout guidance in this slice.

Reason:
The operator explicitly stated that Dashboard has no substantive issue beyond minor layout tuning, while the real issues are in other apps/functions.

Implications:
- avoid reopening dashboard/rotator architecture
- focus implementation and testing on shell-owned app flows plus Photos child behavior

Supersedes:
- archived shell-repair planning state as the current active workstream

---

DECISION ID: D-016
Status: ACTIVE

Topic:
Photos interaction contract

Decision:
Photos should match dashboard-style touch interaction: tap left for previous, tap right for next, and hold to exit back to the shell.

Reason:
The operator explicitly requested parity with Dashboard touch behavior for Photos.

Implications:
- `modules/photos/slideshow.py` must own left/right/hold behavior while active
- the shell must not compete for the same gesture path during active Photos runtime

Supersedes:
None

---

DECISION ID: D-017
Status: ACTIVE

Topic:
Settings content level

Decision:
Settings screens should render concise operator-summary content for Network, Pi Stats, and Logs instead of placeholder-only screens.

Reason:
The operator selected operator-summary status content and shell stack service logs as the desired output.

Implications:
- implement fallback-safe, read-only data gathering in the shell
- preserve the existing `stats.png`-based screen model and strip-only back behavior

Supersedes:
None

---

DECISION ID: D-018
Status: ACTIVE

Topic:
Theme picker scaling model

Decision:
Themes should use a generated single-screen picker with deterministic touch mapping for discovered themes, supporting up to 6 installed themes without paging.

Reason:
The operator clarified that theme rendering will need to adapt to installed themes and there will not be more than 6 active themes.

Implications:
- remove hardcoded three-theme assumptions from the theme picker logic
- keep the behavior shell-local in `boot/boot_selector.py`
- keep persistence immediate and remain on the Themes screen after apply

Supersedes:
- archived three-column-only theme picker assumption for future work

---

DECISION ID: D-019
Status: ACTIVE

Topic:
Dashboard layout tuning surface

Decision:
Dashboard layout tuning remains narrow and uses existing global and script-local knobs instead of a structural layout rewrite.

Reason:
The operator asked where margins can be adjusted and did not request a dashboard redesign.

Implications:
- global tuning surface remains `display_layout.py`
- shell status-screen offsets should become explicit named constants in `boot/boot_selector.py`
- script-local offsets remain in the module files that already define them

Supersedes:
None
