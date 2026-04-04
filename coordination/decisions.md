# Architecture Decisions

Live status: idle as of 2026-04-04.

Rules:
- Record only active, reusable decisions here.
- Task-specific completed history belongs in `coordination/archive/`.
- `PLAN.md` is the active task source of truth when a task is open.

---

DECISION ID: D-033
Status: ACTIVE

Topic:
Post-closeout control plane

Decision:
Keep the active control plane minimal between tasks.

Reason:
The NASA delivery slice is complete and archived, and the next task should start from repo reality rather than stale in-progress notes.

Implications:
- `PLAN.md` stays in idle/reset state until the next task starts
- completed task history is archived under `coordination/archive/`
- active coordination files should be created only when the next task actually needs them

Supersedes:
- the completed NASA-slice decision set now archived in `coordination/archive/2026-04-04-nasa-app-closeout.md`
