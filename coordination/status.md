# Project Status

Last updated: 2026-03-14

## Overall

- Active execution plan is `rebuild-plan.md`.
- `PLAN.md` is retained as historical context for the shell-first migration that has already been implemented.
- The current rebuild goal is architecture remediation and hardening on top of the shell-first baseline.

## Baseline State

- Shell-first runtime exists in `boot/boot_selector.py`.
- Dashboards remains the supported dashboards entrypoint in `display_rotator.py`.
- Photos is split into a dedicated slideshow app in `modules/photos/slideshow.py`.
- The first remediation slice has landed on branch `codex/architecture-remediation` as commit `616c169`.

## Verified Work

- Shared framebuffer helpers now exist in `framebuffer.py`.
- Rotator helper extraction exists in `rotator/config.py`, `rotator/backoff.py`, `rotator/discovery.py`, and `rotator/defaults.py`.
- Hardware-free tests for rotator helpers and framebuffer conversion were reported passing for the first remediation slice.

## Open Work

- Rotator decomposition is incomplete: touch handling and screen power logic still need extraction from `display_rotator.py`.
- Error handling and exit-code normalization remain incomplete across modules.
- systemd hardening remains incomplete and still needs explicit review for legacy service coupling.
- README and operator docs still reflect the earlier migration emphasis more than the remediation roadmap.

## Remediation Reset Summary

- The earlier shell/app-split delivery plan solved a product migration goal but did not address the main engineering debt.
- The active problem statement is now:
  - monolithic `display_rotator.py`
  - duplicated framebuffer and RGB565 logic
  - inconsistent failure semantics and exit codes
  - weak privilege and service boundaries
  - fragmented tests
  - incomplete architecture documentation
- The rebuild is now being executed as small remediation slices rather than feature streams.

## Integration Readiness

- The repo is not yet at final rebuild acceptance.
- The correct next work is remediation and hardening, not more feature expansion.
- Feature ideas remain tracked in `coordination/ideas.md` and are out of scope unless explicitly promoted.
