# zero2dash — AGENTS.md

## Purpose and scope

This AGENTS.md is the source of truth for AI coding agents working in this repository.

Current priority: implement a new standalone NASA/ISS app under `~/zero2dash/nasa-app/` that launches from the main menu and renders directly to the framebuffer.

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
- Shell/menu runtime entrypoint: `boot/boot_selector.py` (or whatever the shell entrypoint currently is).
- Dashboards rotator entrypoint: `display_rotator.py`.
- Photos standalone app entrypoint: `modules/photos/slideshow.py` (or the repo’s current Photos app entrypoint).
- systemd units/timers: `systemd/`.
- repo config: `.env` (template usually `.env.example`).

NASA app (new):
- App root directory: `nasa-app/` (must be self-contained).
- App assets/fonts/cache: inside `nasa-app/` only.
- App entrypoint: choose a single obvious script in `nasa-app/` (e.g. `nasa-app/app.py`) and wire the shell to launch it.

Environment reuse:
- Observer lat/lon for “next flyover” must reuse the same `.env` variables the weather module uses.
  Inspect the weather module to confirm variable names and parsing conventions.

## Module contracts (important)

Dashboards are module-based by default:
- Each module typically lives under `modules/<name>/`.
- The rotator typically expects `modules/<name>/display.py` as an entrypoint (unless configured otherwise).

The NASA app is NOT a rotator module:
- Do not add it to dashboard rotation.
- Do not place it under `modules/`.
- Do not edit `display_rotator.py` unless you find a genuine integration dependency (this is unlikely and must be justified).

## Subagent delegation rules (Codex)

This repo uses Codex subagents for parallel work.

Rules:
- The root “Project Manager” agent is the ONLY agent allowed to spawn subagents.
- Subagents must NOT spawn additional subagents.
- Use parallel subagents for read-heavy tasks (exploration, API research, review, validation planning).
- Avoid parallel edits to the same files. If parallel work is needed, split work across disjoint directories/files or use isolated worktrees where supported.

When delegating, the PM must:
- give each subagent a bounded task and an explicit output template
- require summaries (no raw logs) unless logs are specifically requested
- wait for all delegated results before starting implementation

Recommended thread/depth settings (if configurable):
- [agents] max_threads = 6
- [agents] max_depth = 1

## Safety, permissions, and secrets

Non-negotiables:
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

## NASA app requirements reminder (summary)

The NASA app must:
- be standalone under `~/zero2dash/nasa-app/`
- render directly to framebuffer
- cycle pages every 10 seconds
- refresh ISS location/details every 2 minutes while running
- fetch crew once on launch
- support overflow crew pages when needed
- cache to JSON (location and crew caches separate)
- show stale-data warnings only on affected pages
- show a dedicated error screen if startup fails and no cache exists
- integrate into main menu: page 1, bottom-left yellow tile
- update global Home long-press from 3 seconds to 2 seconds
- respect touch rule: left strip is back/exit everywhere except main menu (where left strip changes pages)

## Validation and safe testing habits

Prefer hardware-safe validation first:
- Provide a way to render pages without writing to framebuffer:
  - `--no-framebuffer`
  - `--output /tmp/nasa_page.png`
- Provide a lightweight deterministic check:
  - `--self-test` (for parsing/formatting, cache IO, API response handling)
- When network calls are involved, ensure the app can start from cache and display stale warnings correctly.

When you change behaviour, you must:
- update README/docs if there are user-visible changes
- include a short “how to validate” section in your final summary

## Change style

- Make minimal, targeted changes.
- Preserve existing behaviour unless explicitly required.
- Avoid “cleanup” refactors unless requested.
- Keep code readable and consistent with existing conventions.

## Definition of done (for the NASA app task)

Done means the acceptance criteria in the NASA app prompt are met, AND:
- no regressions to dashboards/Photos/systemd/autostart were introduced
- the shell returns cleanly and no orphan child processes remain
- validation flags work without requiring the real framebuffer
