# Architecture Decisions

This file records current-run implementation decisions and clarifications.
`PLAN.md` is the only execution source of truth. This file must not override it.

Rules:
- Mouser or the operator records decisions.
- Recorded entries clarify execution within `PLAN.md`; they do not replace it.
- Archive entries from previous agent teams are non-authoritative.

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

## Current-Run Decisions

DECISION ID: D-001
Status: ACTIVE

Topic:
Shell-first baseline remains accepted

Decision:
`PLAN.md` keeps the shell-first runtime intact while rebuilding the selector:
- `boot/boot_selector.py` remains the long-running parent shell
- `display_rotator.py` remains the dashboards entrypoint
- `modules/photos/slideshow.py` remains the dedicated Photos app entrypoint

Reason:
This behavior already exists in the repo and should be repaired and extended rather than replaced wholesale.

Implications:
- shell launch and return behavior remain the compatibility baseline
- remediation work must preserve child entrypoints unless a later decision explicitly changes them

Supersedes:
None

---

DECISION ID: D-006
Status: ACTIVE

Topic:
Shell child stop and reclaim policy

Decision:
Shell reclaim behavior is graceful stop first, then force-kill if required. The shell must not reclaim framebuffer control or redraw until the child process is confirmed exited.

Reason:
The operator selected this reclaim policy and downstream flows already rely on it.

Implications:
- home long-press and other reclaim paths must use this stop path
- framebuffer ownership remains exit-gated

Supersedes:
None

---

DECISION ID: D-007
Status: ACTIVE

Topic:
Mode-switch request transport

Decision:
The shell mode-switch interface uses a request-file transport for `menu`, `dashboards`, `photos`, and `night`.

Reason:
The operator selected a simple transport and the current shell already exposes it.

Implications:
- timers and services should request shell modes instead of competing for foreground ownership
- `handle_mode_request()` remains the routing point for approved shell modes

Supersedes:
None

---

DECISION ID: D-009
Status: ACTIVE

Topic:
Active plan source

Decision:
`PLAN.md` is the active execution plan for the current shell repair and asset-backed menu rebuild.

Reason:
The operator explicitly directed this run to follow `PLAN.md`, and the repo state now matches that target better than the stale rebuild coordination layer.

Implications:
- coordination, tasking, and reviews must align to `PLAN.md`
- stale references from archived coordination entries are informational history only

Supersedes:
- archived previous-team plan references

---

DECISION ID: D-010
Status: ACTIVE

Topic:
Theme-backed shell rebuild scope

Decision:
The shell rewrite in this run includes the menu/model rebuild described in `PLAN.md`, bound to the real assets under `themes/*`, while preserving the accepted shell-first runtime and existing child entrypoints.

Reason:
The operator explicitly promoted the theme-backed shell rebuild into active scope for this run.

Implications:
- `boot/boot_selector.py` must move from the paged tile model to explicit themed screens
- old generic boot selector assets are not the routing contract for this run
- NASA ISS is a shell-owned placeholder in this slice

Supersedes:
- archived previous-team scope notes

---

DECISION ID: D-011
Status: ACTIVE

Topic:
Framebuffer API hotfix scope

Decision:
Keep the Pi startup fix shell-local in `boot/boot_selector.py` by adding a compatibility writer that accepts either `write_frame()` or legacy `write_image()` methods.

Reason:
The Pi failure is isolated to the selector startup/render path. The shared framebuffer module already exposes the correct `write_frame()` contract, so the smallest safe fix is to adapt the caller instead of widening the framebuffer surface during smoke testing.

Implications:
- unblocks Pi shell startup without changing `framebuffer.py`
- preserves compatibility if any selector test doubles still expose `write_image()`
- keeps the hotfix narrow and reversible

Supersedes:
None

---

DECISION ID: D-012
Status: ACTIVE

Topic:
Theme persistence failure policy

Decision:
Theme persistence must be best-effort only. If the selector cannot update its theme-state file, it should log the error and continue booting with the currently selected theme instead of aborting startup.

Reason:
Pi smoke testing showed that a permissions issue on `/tmp/zero2dash-shell-theme` can prevent the entire shell from starting. Theme persistence is not critical enough to justify a boot failure.

Implications:
- the shell remains bootable even when the theme-state file is stale or owned by another user
- startup robustness is prioritized over atomic persistence in this path
- Pi validation can proceed without requiring manual cleanup of temp-state files

Supersedes:
None

---

DECISION ID: D-013
Status: ACTIVE

Topic:
Default theme-state storage

Decision:
Default theme-state persistence should use a user-scoped state path rather than a shared file under `/tmp`.

Reason:
Pi smoke testing showed that the shared temp-file default creates cross-user ownership conflicts between service runs and manual runs. Theme persistence needs to be stable without requiring cleanup of root-owned temp files.

Implications:
- default theme persistence becomes per-user unless explicitly overridden with `BOOT_SELECTOR_THEME_STATE_PATH`
- manual Pi testing no longer collides with the service by default
- service units can still pin a different state path explicitly if they need shared behavior

Supersedes:
None

---

## Archive Note

- Previous-team decision logs are archive material only.
- They may explain how the repo got here, but they are not authoritative for this run.
