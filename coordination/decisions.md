# Architecture Decisions

Live status: RESET on 2026-03-28.

Rules:
- Mouser or the operator records decisions.
- Recorded entries clarify execution within `PLAN.md`; they do not replace it.

---

DECISION ID: D-027
Status: ACTIVE

Topic:
Active slice priority

Decision:
Treat NASA / ISS app stabilization and delivery as the only active implementation slice.

Reason:
The previous shell stabilization slice is complete, and the operator has now reopened NASA as the current priority.

Implications:
- do not keep reporting the finished shell slice as active work
- align the control plane around `nasa-app/`
- preserve dashboards, Photos, and systemd/autostart unless explicitly reopened

Supersedes:
- shell-slice-only active priority wording

---

DECISION ID: D-028
Status: ACTIVE

Topic:
NASA data stack

Decision:
Keep `wheretheiss.at` as primary ISS telemetry, keep Corquaid as primary crew metadata, and use Open Notify to restore observer pass/flyover behavior while retaining its narrow fallback role where helpful.

Reason:
`wheretheiss.at` and Corquaid provide the richer telemetry and crew metadata the current UI expects, while Open Notify is the best fit for restoring the original observer pass/flyover requirement.

Implications:
- do not switch the entire app to Open Notify as the primary source
- restore pass/flyover support using observer coordinates
- handle live pass lookup failure with cached stale pass data if available

Supersedes:
- older wording that treated flyover as permanently removed

---

DECISION ID: D-029
Status: ACTIVE

Topic:
Map rendering contract

Decision:
The location page must use `map.png` and accurate plotting calibrated to the visible map art.

Reason:
The operator reported that the current map page uses the wrong assets and that the current marker/trail placement does not appear relevant to the actual map image.

Implications:
- switch away from the current `iss-background.png` map usage
- calibrate the drawing bounds for the real map art
- treat inaccurate plotting as a correctness bug, not a cosmetic issue

Supersedes:
- the current generic full-canvas plotting assumption

---

DECISION ID: D-030
Status: ACTIVE

Topic:
Startup behavior

Decision:
Improve startup speed and also provide a loading screen so the app never appears blank for long.

Reason:
The operator reports 7-10 second startup latency, which is too slow even if some network work remains unavoidable.

Implications:
- render a useful first frame quickly from cache or a loading screen
- defer non-critical fetches behind the first visible frame where safe
- treat a long blank wait as a shipped bug

Supersedes:
- the current fully blocking startup experience

---

DECISION ID: D-031
Status: ACTIVE

Topic:
Operator-tunable layout controls

Decision:
NASA page text/layout/font controls remain code-only and must be clearly marked and briefly explained in code.

Reason:
The operator wants to hand-tune text placement, sizing, and fonts directly in code rather than through a UI.

Implications:
- centralize the relevant constants in `nasa-app/app.py`
- expose position, area, font path, font size, and formatting controls
- add short comments telling the operator what to edit

Supersedes:
- the current scattered and underexplained layout values

---

DECISION ID: D-032
Status: ACTIVE

Topic:
Delegation model

Decision:
Use Pathfinder for discovery, Switchboard for runtime implementation, Sentinel for validation, Curator for docs, and Framekeeper only if asset support becomes necessary.

Reason:
The active NASA work can be split cleanly by responsibility, but the core runtime work must stay serial because it centers on `nasa-app/app.py`.

Implications:
- parallelize read-heavy discovery and review
- serialize implementation on the NASA runtime and tests
- keep shell edits separate and minimal

Supersedes:
- the shell-slice delegation assignments
