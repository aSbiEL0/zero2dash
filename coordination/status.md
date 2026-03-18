# Project Status

Last updated: 2026-03-18

## Current Software State

- The active execution plan is `rebuild-plan.md`; `PLAN.md` is historical only.
- The software baseline is shell-first:
  - `boot/boot_selector.py` is the long-running shell
  - `display_rotator.py` remains the dashboards entrypoint
  - `modules/photos/slideshow.py` remains the Photos entrypoint
- Shared framebuffer logic exists in `framebuffer.py`.
- Rotator internals have been split out into `rotator/*`, including touch, power, config, backoff, discovery, and defaults.
- Rebuild documentation and operator guidance have been refreshed to describe the remediation architecture rather than the older migration.

## Rebuild Work Already Landed

- `R-000` control-plane cleanup is complete.
- `R-001` rotator touch and screen-power extraction is complete.
- `R-002` framebuffer consolidation is complete.
- `R-003` service-boundary hardening and documentation pass is complete.
- `R-004` docs and validation guidance refresh is complete.
- `R-005` shell contract documentation is complete.

## What Still Needs Looking At

- Failure semantics are still not normalized across the runtime. Genuine render and refresh failures do not yet fail consistently enough.
- Pi validation is still required for hardware-owned behavior:
  - dashboard launch flow
  - Photos touch navigation and exit behavior
  - screen-power behavior
  - service interaction under the real selector/menu baseline
- The current selector/menu baseline needs explicit review so the operator can separate accepted baseline behavior from future redesign work.
- Service/runtime coupling should be rechecked on hardware even after the documentation hardening pass.
- Some test coverage still needs extending where the extracted logic now makes that practical.

## Operator-Sealed Decisions

- Shell child reclaim is graceful-then-kill, with framebuffer reclaim only after child exit.
- Shell mode switching uses a request-file transport.
- Full boot menu redesign is separate follow-up scope, not an implicit rebuild deliverable.

## Scope Discipline

- The rebuild is still a remediation and hardening pass, not feature expansion.
- Feature ideas remain tracked in `coordination/ideas.md`.
- New UI or selector redesign work should only start when explicitly promoted into its own task slice.
