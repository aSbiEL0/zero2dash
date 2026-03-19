# NASA App Review - 2026-03-19

## Scope

This document summarizes a read-only forensic review of the current NASA/ISS app and shell integration against:

- [AGENTS.md](/C:/codex/nasa-app/AGENTS.md)
- [task_plan.md](/C:/codex/nasa-app/task_plan.md)

The goal was bug finding and error analysis first, with emphasis on whether the current implementation matches the original acceptance target and where the UI/runtime quality breaks down.

## Executive Summary

The app is partially working, but it is not cleanly aligned with the stated requirements or the expected UX quality.

What is solid:

- NASA launch wiring from the shell is present.
- Page cycle timing and location refresh timing are implemented correctly.
- Crew is fetched once on launch and paginated.
- Separate JSON caches exist for location and crew.
- A dedicated startup error screen exists.

What is not solid:

- "Next flyover" is not implemented; it is a permanent placeholder.
- The map page stale-data logic is incorrect in one fallback path.
- The map page layout conflicts with the app's own exit gesture.
- The shell/menu visual contract is fragile because routing and tile art are defined in different places.
- Validation/documentation claims are ahead of the actual test coverage in this checkout.

## Findings

### 1. Flyover Requirement Was Quietly Downgraded

Severity: High

Relevant files:

- [AGENTS.md:45](/C:/codex/nasa-app/AGENTS.md#L45)
- [AGENTS.md:99](/C:/codex/nasa-app/AGENTS.md#L99)
- [task_plan.md:75](/C:/codex/nasa-app/task_plan.md#L75)
- [task_plan.md:195](/C:/codex/nasa-app/task_plan.md#L195)
- [nasa-app/app.py:770](/C:/codex/nasa-app/nasa-app/app.py#L770)
- [nasa-app/app.py:797](/C:/codex/nasa-app/nasa-app/app.py#L797)
- [nasa-app/app.py:1021](/C:/codex/nasa-app/nasa-app/app.py#L1021)

Problem:

The requirements explicitly call for reusing the weather observer coordinates for "next flyover". The implementation never computes that value. Instead, it hardcodes `flyover_status="unavailable"` and `flyover_label="Next flyover unavailable"` in both the live and fallback location builders.

Why this matters:

- The code matches the degraded plan, but not the original requirement.
- Operators will see a feature-shaped placeholder that never becomes real.
- Misconfiguration and "not implemented" currently look the same to the user.

Suggested solutions:

- Option A: implement real flyover computation using the existing observer coordinates and a defensible public-data path.
- Option B: explicitly remove the flyover field from the acceptance target and redesign the details page so it does not promise unavailable functionality.
- Option C: keep the field but label it honestly as "Observer pass times unavailable" and surface diagnostics when coordinates are missing or invalid.

Recommended path:

- If the product requirement is strict, implement it properly.
- If not, remove the fake promise from the UI. A permanent stub is worse than an omitted feature.

### 2. Map Stale-State Logic Is Wrong

Severity: High

Relevant files:

- [nasa-app/app.py:751](/C:/codex/nasa-app/nasa-app/app.py#L751)
- [nasa-app/app.py:776](/C:/codex/nasa-app/nasa-app/app.py#L776)
- [nasa-app/app.py:800](/C:/codex/nasa-app/nasa-app/app.py#L800)
- [nasa-app/app.py:814](/C:/codex/nasa-app/nasa-app/app.py#L814)
- [nasa-app/app.py:974](/C:/codex/nasa-app/nasa-app/app.py#L974)

Problem:

When the app falls back to the secondary location source, it can reuse cached trail/details data while still returning `map_stale=False`. That means the map can show partially stale information without a stale treatment.

Why this matters:

- It breaks the requirement that stale warnings appear only on affected pages.
- It also breaks trust, because the most visual page can quietly show old path data as if it were current.

Suggested solutions:

- Mark the map stale whenever cached trail/location context is reused.
- Split freshness more explicitly:
  - position freshness
  - trail freshness
  - details freshness
- Drive page chrome from those explicit freshness flags instead of a coarse boolean.

Recommended path:

- Introduce a small freshness model and compute map stale based on whether any displayed map data came from cache.

### 3. The Map Page Fights Its Own Touch Model

Severity: High

Relevant files:

- [nasa-app/app.py:59](/C:/codex/nasa-app/nasa-app/app.py#L59)
- [nasa-app/app.py:549](/C:/codex/nasa-app/nasa-app/app.py#L549)
- [nasa-app/app.py:976](/C:/codex/nasa-app/nasa-app/app.py#L976)
- [nasa-app/app.py:989](/C:/codex/nasa-app/nasa-app/app.py#L989)
- [nasa-app/app.py:1024](/C:/codex/nasa-app/nasa-app/app.py#L1024)
- [nasa-app/app.py:1047](/C:/codex/nasa-app/nasa-app/app.py#L1047)

Problem:

The leftmost 32 px are reserved as exit/back, but multiple pages draw content inside or immediately against that strip. The map starts at `x=8`, timestamps start at `x=16`, details text starts at `x=20`, and crew cards start at `x=18`.

Why this matters:

- It causes accidental exits.
- It makes the app feel sloppy even if the data is technically correct.
- It is especially bad on a 320x240 panel with coarse touch targeting.

Suggested solutions:

- Reserve the left strip visually and functionally on every non-menu page.
- Shift all page content right so nothing meaningful starts before `x=LEFT_STRIP_WIDTH + margin`.
- Give the strip intentional UI treatment:
  - back chevron
  - page label
  - subtle contrasting background

Recommended path:

- Treat the left strip as layout chrome, not invisible behavior.

### 4. The Current "World Map" Is Not Production-Grade

Severity: Important

Relevant files:

- [nasa-app/app.py:244](/C:/codex/nasa-app/nasa-app/app.py#L244)
- [nasa-app/app.py:973](/C:/codex/nasa-app/nasa-app/app.py#L973)

Problem:

The map is a generated polygon sketch rather than a credible visualization. It reads as improvised art rather than a deliberate product surface.

Why this matters:

- This is the first page many users will see.
- The visual quality drags down the entire app, even when the rest of the logic is functional.
- It undermines confidence in the data.

Suggested solutions:

- Replace the generated map with a purpose-made static world map asset designed for 320x240.
- Simplify the visual grammar:
  - one clean map panel
  - one strong ISS marker
  - one minimal orbit trail
  - one legible title/status strip
- If map fidelity cannot be made good at this size, reduce ambition:
  - show a clean location card instead of a pseudo-cartographic view.

Recommended path:

- Use a curated static asset and simplify overlays. Do not keep the hand-drawn polygon map.

### 5. Page Identity Is Too Weak For An Auto-Cycling App

Severity: Important

Relevant files:

- [display_layout.py](/C:/codex/nasa-app/display_layout.py)
- [nasa-app/app.py:994](/C:/codex/nasa-app/nasa-app/app.py#L994)
- [nasa-app/app.py:1030](/C:/codex/nasa-app/nasa-app/app.py#L1030)
- [nasa-app/app.py:1037](/C:/codex/nasa-app/nasa-app/app.py#L1037)

Problem:

The app cycles every 10 seconds, but page identity is weak. The map page has no clear heading, the details page is dense and unlabeled, and the crew page relies on a small `1/2` marker in the corner.

Why this matters:

- Users need to recognize the page instantly.
- Auto-cycling magnifies weak hierarchy.

Suggested solutions:

- Add strong page headers:
  - `ISS Position`
  - `ISS Details`
  - `Crew`
- Use a consistent top bar across all NASA pages.
- Keep per-page content limited to one primary task.

Recommended path:

- Rebuild the page set around a shared layout skeleton with explicit page titles.

### 6. Menu Routing And Menu Visuals Drift Independently

Severity: Important

Relevant files:

- [boot/boot_selector.py:123](/C:/codex/nasa-app/boot/boot_selector.py#L123)
- [boot/boot_selector.py:869](/C:/codex/nasa-app/boot/boot_selector.py#L869)
- [boot/boot_selector.py:880](/C:/codex/nasa-app/boot/boot_selector.py#L880)
- [boot/boot_selector.py:1454](/C:/codex/nasa-app/boot/boot_selector.py#L1454)
- [boot/nasa_menu.py:14](/C:/codex/nasa-app/boot/nasa_menu.py#L14)
- [boot/nasa_menu.py:21](/C:/codex/nasa-app/boot/nasa_menu.py#L21)

Problem:

The live shell uses theme PNGs plus quadrant math. A separate helper file describes a yellow NASA tile, but the running shell does not depend on that file. Functionally, NASA is in the bottom-left slot. Visually, that depends entirely on theme art matching the code.

Why this matters:

- The requirement says "page 1, bottom-left yellow tile".
- The code only enforces bottom-left.
- Yellow tile appearance can drift theme by theme with no code-level protection.

Suggested solutions:

- Option A: generate tiles in code so visuals and hit regions are one contract.
- Option B: keep theme assets, but add a validation rule that checks tile color/position metadata per theme.
- Option C: remove the dead/alternate menu definition if it is no longer authoritative.

Recommended path:

- Either generate the menu in code or formalize theme metadata. The current split contract is fragile.

### 7. Validation Claims Are Stronger Than The Actual Repo State

Severity: Medium

Relevant files:

- [README.md:16](/C:/codex/nasa-app/README.md#L16)
- [README.md:82](/C:/codex/nasa-app/README.md#L82)

Problem:

The README references `shell-mode-switch@.service` and multiple unit-test modules, but this checkout does not contain the referenced `tests/` tree.

Why this matters:

- It inflates confidence in the current validation story.
- Reviewers and operators can waste time trying to run checks that do not exist.

Suggested solutions:

- Update the README to match the actual repo state.
- Or restore the missing tests if they are supposed to exist.
- Add NASA-specific tests for:
  - stale-state calculation
  - cache round-trip
  - startup error path
  - page pagination
  - shell launch mapping

Recommended path:

- Fix the docs immediately, then add targeted regression tests instead of relying only on inline smoke tests.

## Proposed Remediation Strategy

### Phase 1: Correctness Fixes

Target:

- Make the current feature truthful and internally consistent.

Actions:

- Fix stale-state calculation on the map page.
- Decide the fate of flyover:
  - implement it, or
  - remove the placeholder promise from the UI/spec.
- Surface invalid observer config as diagnostics instead of silently downgrading to `None`.

### Phase 2: Layout Repair

Target:

- Stop the app from fighting its own touch model.

Actions:

- Reserve the left strip visually on every app page.
- Move all content out of the exit zone.
- Introduce one shared page scaffold for NASA pages:
  - left nav strip
  - top title/status bar
  - main content panel
  - bottom freshness/footer region

### Phase 3: Visual Redesign

Target:

- Replace the improvised map and weak page hierarchy.

Actions:

- Replace the generated world map with a curated static asset.
- Simplify the map page.
- Make the details page less crowded.
- Make the crew page feel like a real roster rather than stacked debug cards.

### Phase 4: Shell/Menu Contract Cleanup

Target:

- Make tile appearance and tile behavior a single coherent contract.

Actions:

- Either render menu tiles in code or add metadata-driven theme validation.
- Remove or clearly deprecate [boot/nasa_menu.py](/C:/codex/nasa-app/boot/nasa_menu.py) if it is not authoritative.

### Phase 5: Validation Repair

Target:

- Make the repo's claimed validation story true.

Actions:

- Align README with actual available tests and services.
- Add a small `tests/` suite for NASA logic and shell mapping.

## Suggested Brief For The Implementation Agent

If this is handed off for fixes, the first pass should focus on:

1. Fix stale-state correctness on the map page.
2. Remove content from the left exit strip and establish a shared NASA page layout.
3. Replace the generated map with a proper asset or a simpler card-based location view.
4. Resolve the flyover requirement honestly:
   - implement it, or
   - remove the dead placeholder contract.
5. Clean up the shell/menu visual contract so the NASA tile is not theme-art roulette.

## Validation Notes

What was confirmed:

- Static code inspection across the NASA app, shell integration, and docs.
- Syntax compilation passed via `py_compile` for the reviewed Python files.

What was not fully confirmed:

- Runtime rendering on the actual Pi display.
- Real touch behavior on hardware.
- Screenshot-based visual verification in this environment.

Why runtime validation was limited:

- Available local Python environments were mismatched for running Pillow-based smoke tests directly in this session.
