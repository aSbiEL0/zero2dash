# Zero2Dash Debug Campaign

Purpose: Track the approved debugging and hardening roadmap in execution order.

## Operator Rules

- Codex must follow the dependency map in this file.
- Codex must not skip dependency checks.
- Codex must update task rows after each task.
- Codex must keep fixes minimal and scoped.
- Codex must not remove completed task history.
- Codex must report blockers instead of guessing.

## Status Legend

- TODO
- READY
- IN_PROGRESS
- BLOCKED
- COMPLETE
- VERIFIED

---

## 1. Recommended Execution Order

| Order | Task ID | Title | Reason |
|------|------|------|------|
| 1 | 01 | Centralised config validation with safe defaults | Foundation for guided startup behaviour |
| 2 | 25 | Align README and systemd unit references | Foundation for deployment consistency |
| 3 | 16 | Fix Google Photos album item fetch | Immediate functional blocker |
| 4 | 02 | Fix cross-midnight active-hours logic | Immediate functional blocker |
| 5 | 08 | Add HTTP/HTTPS support for Pi-hole | Pi-hole core |
| 6 | 09 | Validate Pi-hole auth prerequisites | Pi-hole core |
| 7 | 10 | Preserve root-cause exceptions in Pi-hole API flow | Pi-hole core |
| 8 | 11 | Add framebuffer write guards and fallback output mode | Pi-hole core |
| 9 | 12 | Introduce staged Calendar config bootstrap | Calendar core |
| 10 | 13 | Expand Calendar retry policy | Calendar core |
| 11 | 14 | Harden Calendar headless OAuth flow | Calendar core |
| 12 | 15 | Strengthen Calendar token scope validation | Calendar core |
| 13 | 21 | Improve Photos credential bootstrap | Photos core |
| 14 | 18 | Persist refreshed Photos token | Photos core |
| 15 | 19 | Normalise Photos media download handling | Photos core |
| 16 | 20 | Iterate robustly across album items before failure | Photos core |
| 17 | 17 | Resolve default logo path correctly | Photos core |
| 18 | 03 | Enforce separate token files per Google integration | Shared auth cleanup |
| 19 | 06 | Add screen-power fallback state machine | Rotator stability |
| 20 | 07 | Add per-page failure backoff/quarantine | Rotator stability |
| 21 | 04 | Make rotator exclusions explicit and diagnosable | Rotator diagnostics |
| 22 | 05 | Harden touch-device selection | Rotator diagnostics |
| 23 | 22 | Add Pillow compatibility shim | Portability |
| 24 | 23 | Parameterise framebuffer path and geometry | Portability |
| 25 | 24 | Refactor calendash touch input parsing | Portability |
| 26 | 26 | Make systemd framebuffer-path configurable | System integration |
| 27 | 27 | Add dependency checks in pre-start shell script | System integration |

---

## 2. Dependency Map

| Task ID | Depends On | Notes |
|------|------|------|
| 01 | - | Foundation task |
| 02 | - | Immediate correctness fix |
| 03 | 15, 21 | Apply after Calendar/Photos auth cleanup |
| 04 | - | Independent |
| 05 | 04 | Best after diagnostics are clearer |
| 06 | - | Independent |
| 07 | - | Best after clearer failure behaviour exists |
| 08 | 01 | Reuse shared config patterns |
| 09 | 01 | Reuse shared config patterns |
| 10 | 09 | Better after auth validation is explicit |
| 11 | 01 | Benefits from config groundwork |
| 12 | 01 | Calendar bootstrap depends on config framework |
| 13 | 12 | Better after config/runtime errors are separated |
| 14 | 12 | Better after staged setup exists |
| 15 | 12 | Better after staged setup exists |
| 16 | - | Functional blocker |
| 17 | - | Independent |
| 18 | 21 | Best after credential bootstrap is improved |
| 19 | 16, 18 | Needs correct item fetch and better token behaviour |
| 20 | 16, 19 | Needs correct fetch path and improved download handling |
| 21 | 01 | Benefits from centralised config validation |
| 22 | - | Independent |
| 23 | - | Independent |
| 24 | 23 | Best after input/device config is more flexible |
| 25 | - | Foundation task |
| 26 | 23, 25 | Service config should match capability and docs |
| 27 | 25 | Docs and startup behaviour should align |

---

## 3. Task Tracker

| ID | Status | Title | Area | Depends On | Files Affected | Root Cause | Fix Summary | Validation | Commit | Notes |
|----|--------|-------|------|------------|----------------|------------|-------------|------------|--------|-------|
| 01 | TODO | Centralised config validation with safe defaults | Core config | - |  |  |  |  |  |  |
| 02 | TODO | Fix cross-midnight active-hours logic | Pi-hole dashboard | - |  |  |  |  |  |  |
| 03 | TODO | Enforce separate token files per Google integration | Shared Google auth | 15, 21 |  |  |  |  |  |  |
| 04 | TODO | Make rotator exclusions explicit and diagnosable | Rotator | - |  |  |  |  |  |  |
| 05 | TODO | Harden touch-device selection | Rotator | 04 |  |  |  |  |  |  |
| 06 | TODO | Add screen-power fallback state machine | Rotator | - |  |  |  |  |  |  |
| 07 | TODO | Add per-page failure backoff/quarantine | Rotator | - |  |  |  |  |  |  |
| 08 | TODO | Add HTTP/HTTPS support for Pi-hole | Pi-hole API | 01 |  |  |  |  |  |  |
| 09 | TODO | Validate Pi-hole auth prerequisites | Pi-hole API | 01 |  |  |  |  |  |  |
| 10 | TODO | Preserve root-cause exceptions in Pi-hole API flow | Pi-hole API | 09 |  |  |  |  |  |  |
| 11 | TODO | Add framebuffer write guards and fallback output mode | Display output | 01 |  |  |  |  |  |  |
| 12 | TODO | Introduce staged Calendar config bootstrap | Calendar | 01 |  |  |  |  |  |  |
| 13 | TODO | Expand Calendar retry policy | Calendar | 12 |  |  |  |  |  |  |
| 14 | TODO | Harden Calendar headless OAuth flow | Calendar | 12 |  |  |  |  |  |  |
| 15 | TODO | Strengthen Calendar token scope validation | Calendar | 12 |  |  |  |  |  |  |
| 16 | TODO | Fix Google Photos album item fetch | Photos API | - |  |  |  |  |  |  |
| 17 | TODO | Resolve default logo path correctly | Photos assets | - |  |  |  |  |  |  |
| 18 | TODO | Persist refreshed Photos token | Photos auth | 21 |  |  |  |  |  |  |
| 19 | TODO | Normalise Photos media download handling | Photos download | 16, 18 |  |  |  |  |  |  |
| 20 | TODO | Iterate robustly across album items before failure | Photos download | 16, 19 |  |  |  |  |  |  |
| 21 | TODO | Improve Photos credential bootstrap | Photos auth | 01 |  |  |  |  |  |  |
| 22 | TODO | Add Pillow compatibility shim | Static rendering | - |  |  |  |  |  |  |
| 23 | TODO | Parameterise framebuffer path and geometry | Static rendering | - |  |  |  |  |  |  |
| 24 | TODO | Refactor calendash touch input parsing | Touch input | 23 |  |  |  |  |  |  |
| 25 | TODO | Align README and systemd unit references | Docs/systemd | - |  |  |  |  |  |  |
| 26 | TODO | Make systemd framebuffer-path configurable | systemd | 23, 25 |  |  |  |  |  |  |
| 27 | TODO | Add dependency checks in pre-start shell script | Pre-start script | 25 |  |  |  |  |  |  |

---

## 4. Current Task Gate

Use this section so Codex always knows what it is allowed to do next.

| Next Task ID | Dependency Check | Approved To Start | Notes |
|------|------|------|------|
| 01 | Satisfied | YES | Start here unless already completed |

---

## 5. Session Log

| Date | Task ID | Action | Result | Follow-up |
|------|------|------|------|------|
| YYYY-MM-DD |  |  |  |  |

---

## 6. Git Timeline Rules

- Branch from the latest `main`.
- Keep commits aligned with roadmap order.
- Prefer one task per commit.
- Do not stack unrelated fixes into one commit.
- If a task reveals another issue, note it in **Notes** first.
- Update this file before and after each task.
- Before rebasing or merging, confirm tracker changes are committed.

---

## 7. Completion Checklist

- [ ] Foundation tasks complete
- [ ] Functional blockers complete
- [ ] Pi-hole core tasks complete
- [ ] Calendar core tasks complete
- [ ] Photos core tasks complete
- [ ] Rotator stability tasks complete
- [ ] Portability/system tasks complete
- [ ] All tasks verified
- [ ] Docs and service references aligned
