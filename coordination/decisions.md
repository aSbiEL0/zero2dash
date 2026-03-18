# Architecture Decisions

This file records confirmed decisions so agents do not drift.

Rules:
- Only Merlin or the operator records decisions.
- Recorded decisions remain authoritative until superseded.

---

## Decision Template

DECISION ID: D-XXX  
Status: ACTIVE | SUPERSEDED  

Topic:
<subject>

Decision:
<final decision>

Reason:
<why this decision was made>

Implications:
- system behavior change
- architectural constraints
- affected components

Supersedes:
<previous decision if any>

---

## Recorded Decisions

DECISION ID: D-001  
Status: ACTIVE  

Topic:
Shell-first baseline remains accepted

Decision:
The shell-first runtime remains the accepted baseline for the rebuild:
- `boot/boot_selector.py` remains the long-running parent shell
- `display_rotator.py` remains the dashboards entrypoint
- `modules/photos/slideshow.py` remains the dedicated Photos app entrypoint

Reason:
This behavior already exists in the repo and should be hardened and cleaned up rather than re-litigated by default.

Implications:
- remediation work must preserve shell launch/return behavior unless a later decision explicitly changes it
- feature work does not take priority over reliability and architecture cleanup

Supersedes:
None

---

DECISION ID: D-002  
Status: ACTIVE  

Topic:
Active plan source

Decision:
`rebuild-plan.md` is the active execution plan for the current rebuild. `PLAN.md` is historical context only.

Reason:
The older shell/app-split migration plan no longer matches the main engineering problems being solved.

Implications:
- new tasks, status, and reviews must align to `rebuild-plan.md`
- stale shell-split task completion is not treated as rebuild completion

Supersedes:
None

---

DECISION ID: D-003  
Status: ACTIVE  

Topic:
First remediation slice accepted

Decision:
The first remediation slice on branch `codex/architecture-remediation` at commit `616c169` is accepted as the starting point for further rebuild work.

Reason:
It already centralizes shared framebuffer helpers, extracts initial rotator helpers, and adds hardware-free tests without discarding the shell-first baseline.

Implications:
- future remediation tasks should build on `framebuffer.py` and `rotator/*`
- this slice should not be redone from scratch unless a concrete defect is found

Supersedes:
None

---

DECISION ID: D-R-005-1  
Status: ACTIVE  

Topic:
Shell App Registry (AppSpec)

Decision:
The shell maintains a canonical AppSpec registry that feeds the touch menu and any future mode-switching interface. Each AppSpec must supply `id`, `label`, `menu_page`, `tile_index`, `kind`, `launch_command`, `preview_asset`, and `supports_home_gesture`. The shell uses `menu_page`/`tile_index` to place tiles on the quadrant menu, `kind` to signal whether the tile launches Dashboards, Photos, or a night-mode service, and `launch_command` to either call `systemctl start` (when running under systemd) or fall back to the direct binary/script path. `preview_asset` keeps the selectors consistent with the onboarding assets in `boot/`, and `supports_home_gesture` flags whether a long-press should interrupt the child app and return control to this AppSpec.

Reason:
Task R-005 asks us to stabilise the assumptions around the shell app registry so Relay, Iris, and Forge can build their pieces against the same metadata contract without needing to rediscover it.

Implications:
- Any new shell tile or child app must provide every AppSpec field above; omission risks a misaligned menu or missing guardrails.
- For now, the registry is implied by the CLI arguments and constants in `boot/boot_selector.py` (`args.day_service`, `MAIN_MENU_*`, etc.), so the documented contract does not change runtime behavior but ensures future refactors stay compatible.
- Merlin needs to confirm the physical storage of the registry (modules metadata, a JSON manifest, etc.) and clarify how strictly `supports_home_gesture` is enforced relative to the future Home long-press handler.

Supersedes:
None

---

DECISION ID: D-R-005-2  
Status: ACTIVE  

Topic:
Shell App Lifecycle

Decision:
The shell's lifecycle contract for child apps is to start the requested child via `launch_service`, `run_player`, or `run_shutdown`, observe the start outcome, and then return to the shell so the menu can resume once the child stops or fails. `launch_service` calls `systemctl start <service>` when `INVOCATION_ID` is present and falls back to `_launch_direct_mode()` (via `execv` on the direct command) in manual runs. `run_player`/`run_shutdown` shell out via `subprocess.run`. Reasserting shell control (for example via the Home long-press gesture described in the stream responsibilities) is an explicit expectation, even though no handler currently interrupts a running child.

Reason:
Recording this ensures we keep the existing behavior (systemd vs manual start paths and the simple return-to-shell flow) and gives Relay/Iris the ground truth for what counts as a successful launch and how the child lifecycle is supposed to look.

Implications:
- Shell mode transitions must continue to use `launch_service` or the player/shutdown runners to keep behavior unchanged while future logic builds on top of them.
- Because the shell now only regains control when those commands exit, any future Home gesture or watchdog logic must integrate with this same path rather than introducing a parallel start/stop mechanism.
- Stop and reclaim policy is now fixed by `D-006`, which defines graceful-then-kill behavior and exit-gated framebuffer reclaim for this rebuild.

Supersedes:
None

---

DECISION ID: D-R-005-3  
Status: ACTIVE  

Topic:
Shell Mode-Switch Interface

Decision:
The shell exposes a mode-switch interface driven by explicit mode requests that reference the pre-defined `SHELL_MODES` (`menu`, `dashboards`, `photos`, `night`). `handle_mode_request(request)` evaluates `request.target_mode`, ensures the appropriate AppSpec tile is launched (or the menu screen is restored), and keeps the mode state synchronized with timer-triggered requests or operator-invoked changes. Mode requests must never introduce modes beyond the approved set, and the shell remains purely responsible for launching the target child app via its associated AppSpec `launch_command`.

Reason:
Task R-005 calls for documenting the interaction surface so Forge and other streams can wire timers or commands into it without guessing how those requests are interpreted.

Implications:
- Timers or systemd units must call into this interface (or whatever RPC/IPC layer backs it) rather than independently starting new services, to avoid competing for `/dev/fb1`.
- The AppSpec registry described above is the single source that maps each `SHELL_MODE` to a launch command, preview assets, and `supports_home_gesture`.
- Request transport is now fixed by `D-007`, which selects a request-file transport for this rebuild while leaving concrete implementation work to the appropriate stream.

Supersedes:
None

---

DECISION ID: D-006  
Status: ACTIVE  

Topic:
Shell child stop and reclaim policy

Decision:
During this rebuild, shell reclaim behavior is implemented as graceful stop first, then force-kill if required.
- The shell requests child shutdown via the canonical stop path.
- Child apps are expected to exit on graceful termination within a short timeout.
- If the child does not exit in time, force-kill is permitted.
- The shell must not reclaim framebuffer control or redraw the menu until the child process is confirmed exited.

Reason:
The operator selected `Graceful then kill` to make reclaim behavior concrete and safe for the rebuild.

Implications:
- Home long-press and any reclaim flow must use this stop path.
- Force-kill is an explicit fallback, not a parallel normal path.
- Forge and Atlas should treat framebuffer ownership handoff as exit-gated.

Supersedes:
The open reclaim-policy ambiguity noted in `D-R-005-2`

---

DECISION ID: D-007  
Status: ACTIVE  

Topic:
Mode-switch request transport

Decision:
During this rebuild, the shell mode-switch interface uses a simple request-file transport.
- Timers and services request `menu`, `dashboards`, `photos`, or `night` by writing a mode request file consumed by the shell.
- No heavier IPC mechanism is introduced in this rebuild unless the operator later supersedes this decision.

Reason:
The operator selected `Simple request file` as the mode-switch transport for the rebuild.

Implications:
- `handle_mode_request` should be designed around file-delivered requests.
- systemd timers and services must target the request-file path instead of directly competing for foreground ownership.
- Any request schema work should assume file serialization first.

Supersedes:
The open request-transport ambiguity noted in `D-R-005-3`

---

DECISION ID: D-008  
Status: ACTIVE  

Topic:
Boot menu redesign scope

Decision:
The finalized boot menu redesign is not part of the required architecture-remediation rebuild scope.
- It remains a separate follow-up slice unless a minimal compatibility change is required to support the shell contracts being rebuilt.

Reason:
The operator selected `Separate follow-up` to keep the rebuild focused on remediation and hardening.

Implications:
- Relay, Forge, Atlas, and Quill should not expand remediation tasks into full menu or UI redesign work.
- Documentation may mention the redesign as future work, but not as a rebuild deliverable.
- Any shell or menu changes in this rebuild must be narrowly justified by lifecycle or mode-switch contract needs.

Supersedes:
None
