# NASA/ISS App Task Plan

## Mission Brief

- Identity: Orion, root Project Manager for the zero2dash standalone NASA/ISS app delivery.
- Responsibility boundaries: own delegation, integration decisions, minimal diffs, validation, and acceptance closure; avoid unrelated refactors and preserve dashboards, Photos, systemd/timers, and autostart behavior.
- Risk posture: smallest defensible change, no bluffing on unreliable API fields, no new dependencies without approval, no system-level changes without approval.

## Pre-Selected Team

- `nasa_repo_explorer`: map repo-specific launch, rendering, touch, Home hold, and env reuse points.
- `nasa_api_data`: choose public APIs, define cache schema, and document fallbacks for unreliable fields.
- `nasa_ui_rendering`: fit the NASA/ISS experience into the repo's 320x240 framebuffer rendering conventions.
- `nasa_shell_integrator`: identify the minimum menu/shell edits required for launch and global input timing updates.
- `nasa_qa_validator`: define acceptance criteria and safe validation commands before implementation.

## Definition Of Done

- Standalone app exists under `nasa-app/` and is not part of dashboard rotation.
- App renders directly to framebuffer and supports safe validation without framebuffer access.
- Page cycle is 10 seconds across map, details, and crew/overflow pages.
- ISS location/details refresh every 2 minutes while running.
- Crew data is fetched once on launch and split across overflow pages when needed.
- Public free APIs are used with explicit fallback rules for unreliable or missing fields.
- Location/details cache and crew cache are separate JSON files in `nasa-app/`.
- Stale warnings appear only on affected pages.
- Startup failure with no usable cache shows the dedicated error screen.
- Main menu integration places NASA on page 1, bottom-left yellow tile.
- Global Home long-press is changed from 3 seconds to 2 seconds.
- Left-strip touch behavior remains: menu changes pages, app uses back/exit.
- No regressions are introduced to dashboards, Photos, systemd/timers, or autostart.

## Status

- Discovery in progress.
- Waiting for five mandatory subagent reports before the implementation plan is finalized.

## Consolidated Plan

### Repo-Specific Architecture Map

- Menu launch flow: `boot/boot_selector.py`
  - fixed main menu actions: `MAIN_MENU_HOME`, `MAIN_MENU_INFO`, `MAIN_MENU_PADLOCK`, `MAIN_MENU_SHUTDOWN`
  - touch zones: `main_menu_regions()`
  - action dispatch: `resolve_main_menu_action()` and `main()`
  - existing standalone launch pattern: `run_player()`
- Framebuffer helpers and rendering conventions:
  - framebuffer writer pattern: `boot/boot_selector.py::FramebufferWriter`, `modules/trams/display.py::FramebufferWriter`
  - RGB565 conversion: `boot/boot_selector.py::rgb888_to_rgb565`
  - shared text layout helpers: `display_layout.py`
  - validation-friendly CLI patterns: `modules/weather/display.py`, `modules/trams/display.py`, `modules/weather/weather_refresh.py`
- Touch and Home-hold:
  - day rotator Home hold: `display_rotator.py::HOLD_TO_SELECTOR_SECS`
  - blackout Home hold: `modules/blackout/blackout.py::HOLD_TO_SELECTOR_SECS`
  - no existing global left-strip back handler was found; NASA app must implement its own in-app exit behavior
- Weather `.env` reuse:
  - observer coordinates come from `modules/weather/weather_refresh.py::validate_config()`
  - env names are `WEATHER_LAT` and `WEATHER_LON`

### Decisions

- NASA app will be a new standalone directory: `nasa-app/`
  - entrypoint: `nasa-app/app.py`
  - assets/fonts/caches stay inside `nasa-app/`
- API selection:
  - location/details primary: `wheretheiss.at`
  - location/details fallback: Open Notify `iss-now.json`
  - crew primary: Corquaid ISS API `people-in-space.json`
  - crew fallback: Open Notify `astros.json`
- Orbit path:
  - implement a short sampled trail using `wheretheiss.at` positions if available
  - fall back to marker-only if samples fail or wrap badly at the dateline
- Flyover:
  - no bluffing
  - default transparent fallback text: `Next flyover unavailable`
  - reason: no reliable no-auth public pass-time source was verified
- Country/ocean labeling:
  - if `country_code` exists, map it locally to a country name and show country only
  - if not, show `International Waters`
  - do not invent ocean names from coordinates alone
- Crew detail richness:
  - prefer `name + role + current days in space`
  - compute current days only when both `launched` and prior `days_in_space` exist
  - otherwise fall back to stable fields: role, spacecraft, agency
- Menu integration:
  - implement the smallest viable two-page main menu in `boot/boot_selector.py`
  - page 1 gets NASA in the bottom-left tile as required
  - page 2 preserves the existing padlock/photos path
  - main menu left strip toggles pages
- Global Home hold:
  - change default from `3.0` to `2.0` in both `display_rotator.py` and `modules/blackout/blackout.py`

### Rejected Alternatives

- Do not add NASA to the rotator under `modules/`
  - rejected because the task explicitly requires a standalone app and no rotator behavior changes
- Do not add a paid or key-based flyover API
  - rejected because it would require approval and violate the no-bluff requirement for unsupported fields
- Do not add `astropy`, SGP4, or another new orbital dependency
  - rejected because new dependencies require approval and the task can ship honestly without them
- Do not refactor the shell into a generic app registry
  - rejected because the repo is hard-coded today and a broader shell refactor is unnecessary risk

### File Ownership / Edit Scopes

- Shell/menu integration:
  - `boot/boot_selector.py`
  - new or updated boot menu assets under `boot/`
- Global hold timing:
  - `display_rotator.py`
  - `modules/blackout/blackout.py`
- NASA app implementation only:
  - `nasa-app/app.py`
  - `nasa-app/assets/*`
  - `nasa-app/fonts/*`
  - optional `nasa-app/__init__.py` only if needed
- Documentation:
  - `README.md`
  - `boot/README.txt`

### Validation Strategy

- Hardware-safe first:
  - `python nasa-app\\app.py --self-test`
  - `python nasa-app\\app.py --no-framebuffer --output $env:TEMP\\nasa-page.png`
  - page-targeted previews for map/details/crew
  - `python boot\\boot_selector.py --no-framebuffer --show-touch-zones --output-selector $env:TEMP\\boot-selector-preview.png --skip-gif`
- Existing regression smoke checks:
  - weather, trams, calendash, and currency self-tests / preview commands
- Evidence to capture:
  - output PNGs for NASA pages and menu touch zones
  - grep evidence for 2-second hold constants
  - diff review showing no rotator registration or systemd changes

### Risks

- Main menu paging does not exist today, so menu integration is the most regression-sensitive change.
- Orbit trail depends on sampled API data and may need to degrade to marker-only.
- Ocean names and next flyover are not reliably available from no-auth public sources.
- App-local font bundling must be satisfied explicitly because the repo currently relies on system fonts.

## Acceptance Mapping

- Standalone app under `nasa-app/` and not in rotator
  - implementation: `nasa-app/app.py`
  - verify: file tree and no NASA entry under `modules/` or `modules.txt`
- Direct framebuffer rendering
  - implementation: `nasa-app/app.py`
  - verify: framebuffer writer path and `--no-framebuffer` preview support
- Self-contained assets/fonts/caches
  - implementation: `nasa-app/assets/`, `nasa-app/fonts/`, `nasa-app/*.json`
  - verify: app loads only from `nasa-app/`
- 10-second page cycle
  - implementation: `nasa-app/app.py`
  - verify: `--self-test` and code path for page advance timing
- 2-minute ISS refresh while running
  - implementation: `nasa-app/app.py`
  - verify: refresh interval constant and mocked refresh timing test
- Crew fetched once on launch
  - implementation: `nasa-app/app.py`
  - verify: startup fetch flow and cached crew use afterward
- Crew overflow pages
  - implementation: `nasa-app/app.py`
  - verify: mocked long crew list preview produces page 3+
- Separate caches
  - implementation: `nasa-app/location_cache.json`, `nasa-app/crew_cache.json`
  - verify: distinct files and schemas
- Stale warnings only on affected pages
  - implementation: `nasa-app/app.py`
  - verify: forced live failure with cache present per data type
- Startup failure with no cache shows dedicated error screen
  - implementation: `nasa-app/assets/nasa_error.png`, `nasa-app/app.py`
  - verify: forced failure path renders error output
- Main menu integration and NASA tile placement
  - implementation: `boot/boot_selector.py`, `boot/mainmenu*.png`
  - verify: selector preview and region mapping
- Home long-press 2 seconds
  - implementation: `display_rotator.py`, `modules/blackout/blackout.py`
  - verify: constant values and on-device manual confirmation later
- Left-strip touch rule
  - implementation: `boot/boot_selector.py`, `nasa-app/app.py`
  - verify: selector zone preview plus NASA app touch handling code
- Preserve dashboards, Photos, systemd, autostart
  - implementation: no shell refactor beyond selector launch; no changes under `systemd/`; no Photos behavior changes
  - verify: diff review and existing smoke commands

## Decision Log

- Decision: use `wheretheiss.at` plus Open Notify fallback for live position data
  - Alternatives considered: Open Notify only
  - Resolution: rejected because it does not provide altitude/velocity/details
- Decision: use Corquaid as primary crew source
  - Alternatives considered: Open Notify only
  - Resolution: rejected because it lacks role and days-in-space metadata
- Decision: ship flyover as transparent unavailable fallback
  - Objection: requirement asks for next flyover
  - Resolution: accepted requirement intent, rejected fabricated output because the verified no-auth public endpoint is discontinued
- Decision: add a minimal paged menu instead of refactoring the shell
  - Alternatives considered: generic launcher registry
  - Resolution: rejected because it expands scope and regression risk without user value
