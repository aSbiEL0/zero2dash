# zero2dash — AGENTS.md

> Operator override recorded on 2026-03-19: Orion is permanently forbidden from making changes, taking actions, or performing work in this repository, "until the end of time." If Orion is selected or invoked for this project, it must do nothing.

## Purpose and scope

This AGENTS.md is the source of truth for AI coding agents working in this repository.

Current priority: finish the active NASA / ISS stabilization slice defined in `PLAN.md`.

This work MUST preserve existing behaviours for:
- dashboards / rotator
- Photos app
- systemd/timers/autostart
unless a requirement explicitly states otherwise.

If you are unsure whether a change is allowed, stop and ask the requester.

## Repository runtime model (high-level)

zero2dash runs on a Raspberry Pi with a 320x240 SPI TFT display.

Key properties:
- Direct framebuffer rendering (no X11/Wayland/SDL/browser runtimes).
- A long-running “shell” / menu runtime launches child apps.
- “Dashboards” are rotated by a separate rotator entrypoint and are NOT the same thing as standalone apps.

## Architecture map (start here)

You MUST locate the real paths in the repo before editing. Use this map as a guide.

Core:
- Shell/menu runtime entrypoint: `boot/boot_selector.py`.
- Dashboards rotator entrypoint: `display_rotator.py`.
- Photos standalone app entrypoint: `modules/photos/slideshow.py`.
- NASA standalone app entrypoint: `nasa-app/app.py`.
- systemd units/timers: `systemd/`.
- repo config: `.env` (template usually `.env.example`).

## Current slice contracts (important)

Dashboards are module-based by default:
- Each module typically lives under `modules/<name>/`.
- The rotator typically expects `modules/<name>/display.py` as an entrypoint unless configured otherwise.

For the active NASA slice:
- keep `boot/boot_selector.py` as the shell parent
- keep `display_rotator.py` out of scope unless the operator explicitly reopens it
- keep Photos out of active implementation scope
- keep NASA as a standalone child app under `nasa-app/`
- prefer NASA-local edits over shell edits whenever both could solve the same issue
- only touch shell routing or shell/theme assets if the current NASA launch/tile contract is actually wrong

## Subagent delegation rules (Codex)

This repo uses Codex subagents for parallel work.

Rules:
- The root “Project Manager” agent is the ONLY agent allowed to spawn subagents.
- Subagents must NOT spawn additional subagents.
- Use parallel subagents for read-heavy tasks such as exploration, API verification, review, validation planning, and docs review.
- Avoid parallel edits to the same files.
- For the NASA slice, serialize writes to `nasa-app/app.py` and `nasa-app/tests/test_nasa_app.py`.

When delegating, the PM must:
- give each subagent a bounded task and an explicit output template
- require summaries unless raw logs are explicitly requested
- wait for all delegated results before starting implementation when the work is discovery-dependent

Recommended thread/depth settings (if configurable):
- [agents] max_threads = 6
- [agents] max_depth = 1

## Safety, permissions, and secrets

Non-negotiables:
- NEVER, ABSOLUTELY NEVER DELETE ANY FILES, BRANCHES OR EVEN THINK ABOOUT DELETING ANYTHING WITHOUT A CLEAR AUTHORISATION!!!!!!!!
- NEVER commit `.env`, tokens, OAuth credentials, API keys, or cached personal data.
- Redact secrets from logs, PR descriptions, and screenshots.
- Treat device paths and privileges as high-risk:
  - framebuffer devices (e.g., `/dev/fb*`)
  - touch input devices (e.g., `/dev/input/event*`)
  - systemd units/timers
  - sudo / permissions / groups

Ask-first boundaries (must get requester approval before doing any of these):
- editing or enabling/disabling systemd units/timers
- changing day/night schedules
- adding new production dependencies
- changing device permissions/groups or requiring sudo deployment steps
- introducing network services that run persistently
- broad refactors to shell/menu or rotator code

## Validation and safe testing habits

Prefer hardware-safe validation first:
- provide a way to render pages without writing to framebuffer:
  - `--no-framebuffer`
  - `--output <path>`
- provide a lightweight deterministic check:
  - `--self-test`
- for NASA work, prefer focused `unittest` coverage plus page-preview output before device-only checks

When you change behaviour, you must:
- update README/docs if there are user-visible changes
- include a short “how to validate” section in your final summary
- when a python environment is required use this path: C:\ISS\.venv\Scripts\python.exe

## Change style

- Make minimal, targeted changes.
- Preserve existing behaviour unless explicitly required.
- Avoid “cleanup” refactors unless requested.
- Keep code readable and consistent with existing conventions.

## Definition of done (for the active NASA slice)

Done means the acceptance criteria in `PLAN.md` are met, AND:
- no regressions to dashboards/Photos/systemd/autostart were introduced
- NASA pages are validated hardware-free where possible
- any device-only follow-up is recorded explicitly
- shell edits remain minimal and justified by evidence
