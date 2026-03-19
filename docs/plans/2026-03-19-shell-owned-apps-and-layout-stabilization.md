# Shell-Owned Apps and Layout Stabilization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stabilize the remaining shell-owned app flows in Photos, Settings, and Themes, while documenting the exact global and per-screen layout knobs for Dashboard-related margin tuning.

**Architecture:** Keep the shell-first runtime intact. The shell continues to own menus, settings screens, theme selection, and child launch flow in `boot/boot_selector.py`; Photos remains a child app with its own slideshow runtime under `modules/photos/`; Dashboard is not rebuilt and only receives narrow layout guidance through the existing layout constants and script-local offsets.

**Tech Stack:** Python 3.13, argparse-based shell/module CLIs, Pillow image composition, framebuffer-safe render paths, pytest/unittest regression coverage.

---

## Team and Delegation Model

### Primary team

- **Mouser**: orchestration, dependency control, coordination updates, merge order, and cross-boundary approval.
- **Pathfinder**: read-only asset and path verification for themes, status assets, and touch-zone assumptions.
- **Switchboard**: shell/runtime changes in `boot/boot_selector.py`, including Settings and Themes behavior.
- **Photos Worker**: Mouser-approved narrow worker for `modules/photos/*` and the Photos launch/return contract.
- **Sentinel**: regression tests for selector routing, theme mapping, and Photos touch behavior.
- **Curator**: documentation and operator guidance after behavior is stable.

### Parallelization rules

- Pathfinder can run in parallel with Mouser’s coordination reset.
- Photos Worker can run in parallel with Switchboard after Pathfinder confirms current asset and touch assumptions.
- Sentinel starts after the first implementation seam exists, then continues in parallel with the remaining implementation work.
- Curator starts only after Switchboard + Photos Worker + Sentinel are merged and behavior is stable.

### Merge order

1. Mouser coordination reset
2. Pathfinder contract scan
3. Photos Worker stream
4. Switchboard Settings + Themes stream
5. Sentinel regression stream
6. Mouser integration pass
7. Curator documentation pass

---

### Task 1: Reopen the control plane

**Owner:** Mouser  
**Dependencies:** none

**Files:**
- Modify: `PLAN.md`
- Modify: `coordination/tasks.md`
- Modify: `coordination/status.md`
- Modify: `coordination/decisions.md`
- Modify: `coordination/blockers.md`
- Create: `docs/plans/2026-03-19-shell-owned-apps-and-layout-stabilization.md`

**Step 1: Replace the archived active plan**

Write a live `PLAN.md` that points at this plan and makes the new scope explicit:
- Dashboard is not the main remediation target
- Photos, Settings, and Themes are
- Shell-first runtime contracts remain intact

**Step 2: Reopen coordination as live state**

Create active task entries for:
- planning/reset
- Photos touch remediation
- Settings content implementation
- Themes picker generation
- regression tests
- docs follow-up

**Step 3: Record the controlling decisions**

Add decisions for:
- Dashboard remains narrow-layout-only in this slice
- Photos gets dashboard-parity touch behavior
- Settings shows operator-summary content
- Themes supports up to 6 installed themes on one generated picker screen

**Step 4: Commit**

```bash
git add PLAN.md docs/plans/2026-03-19-shell-owned-apps-and-layout-stabilization.md coordination/tasks.md coordination/status.md coordination/decisions.md coordination/blockers.md
git commit -m "docs: reopen planning for shell-owned app stabilization"
```

---

### Task 2: Verify the real asset and mapping contract

**Owner:** Pathfinder  
**Dependencies:** Task 1

**Files:**
- Read: `themes/*`
- Read: `boot/boot_selector.py`
- Read: `modules/photos/slideshow.py`
- Read: `modules/photos/display.py`
- Read: `tests/test_boot_selector.py`
- Read: `tests/test_photos.py`
- Modify: `coordination/status.md`
- Modify: `coordination/decisions.md`

**Step 1: Confirm theme asset inventory**

Verify the currently installed themes, confirm there are no more than 6 active candidates, and note whether the existing `themes.png` art can be reused as a base or must be replaced by generated backgrounds.

**Step 2: Confirm shell-owned screen inventory**

Verify which shell screens use:
- `themes.png`
- `settings.png`
- `stats.png`

Note any hardcoded theme assumptions in `boot/boot_selector.py`.

**Step 3: Confirm Photos runtime seams**

Document:
- where slideshow images advance today
- where touch/gesture events are currently interpreted
- how the shell regains control after Photos exits

**Step 4: Update coordination with verified facts**

Record only verified path and asset contracts. Do not propose new behavior here.

**Step 5: Commit**

```bash
git add coordination/status.md coordination/decisions.md
git commit -m "docs: record verified asset and touch contracts"
```

---

### Task 3: Document and tighten layout knobs without rebuilding Dashboard

**Owner:** Switchboard  
**Dependencies:** Task 2

**Files:**
- Modify: `boot/boot_selector.py`
- Modify: `README.md`
- Test: `tests/test_boot_selector.py`

**Step 1: Isolate shell status text offsets**

If `draw_status_screen()` still uses inline coordinates, replace magic numbers with named constants near the top of the file so shell-owned status screens can be tuned without re-reading the render function.

Suggested names:

```python
STATUS_TITLE_X = 20
STATUS_TITLE_Y = 18
STATUS_BODY_X = 20
STATUS_BODY_Y = 54
```

**Step 2: Preserve existing global Dashboard layout controls**

Do not redesign `display_layout.py`. Keep existing global controls as the dashboard-wide margin surface:

```python
SIDE_MARGIN
HEADER_HEIGHT
ROW_HEIGHT
RIGHT_EXTRA_INSET
```

**Step 3: Document the existing per-script layout knobs**

Add a short README note listing the current script-local margin/offset controls:
- `modules/calendash/calendash-api.py` → `CALENDASH_TEXT_Y_OFFSET`
- `modules/currency/currency-rate.py` → `CONTENT_COLUMN_WIDTH`
- `modules/photos/display.py` → `LOGO_PADDING_RATIO`

**Step 4: Add a narrow regression if constants are extracted**

Add or update a test that confirms `draw_status_screen()` still renders without needing Pi hardware.

**Step 5: Commit**

```bash
git add boot/boot_selector.py README.md tests/test_boot_selector.py
git commit -m "refactor: name shell layout knobs for status screens"
```

---

### Task 4: Give Photos dashboard-parity touch behavior

**Owner:** Photos Worker  
**Dependencies:** Task 2

**Files:**
- Modify: `modules/photos/slideshow.py`
- Modify: `modules/photos/display.py`
- Modify: `boot/boot_selector.py`
- Test: `tests/test_photos.py`
- Test: `tests/test_boot_selector.py`

**Step 1: Write the failing Photos touch tests**

Cover:
- tap left advances to previous image
- tap right advances to next image
- hold exits back to the shell
- Photos does not require the shell to own the gesture while the child is active

Example target behaviors:

```python
def test_slideshow_left_tap_selects_previous_photo(): ...
def test_slideshow_right_tap_selects_next_photo(): ...
def test_slideshow_hold_requests_menu_exit(): ...
```

**Step 2: Run the focused tests to confirm the gap**

Run:

```bash
python -m pytest tests/test_photos.py -q
```

Expected: failing assertions or missing behavior around touch routing.

**Step 3: Implement child-owned Photos touch mapping**

Add the smallest possible touch handling so the Photos child can:
- interpret left-half tap as previous
- interpret right-half tap as next
- interpret hold as exit

Keep the entrypoint contract intact:
- `modules/photos/slideshow.py` remains the runtime entrypoint
- `modules/photos/display.py` remains compatible with existing render helpers

**Step 4: Narrow the shell-side launch contract**

Adjust `boot/boot_selector.py` only as needed so the shell does not compete for gesture ownership while Photos is the foreground child.

**Step 5: Re-run focused tests**

Run:

```bash
python -m pytest tests/test_photos.py tests/test_boot_selector.py -q
```

Expected: Photos navigation and exit tests pass.

**Step 6: Commit**

```bash
git add modules/photos/slideshow.py modules/photos/display.py boot/boot_selector.py tests/test_photos.py tests/test_boot_selector.py
git commit -m "feat: add dashboard-style touch controls to photos"
```

---

### Task 5: Replace Settings placeholders with operator-summary content

**Owner:** Switchboard  
**Dependencies:** Task 2

**Files:**
- Modify: `boot/boot_selector.py`
- Test: `tests/test_boot_selector.py`

**Step 1: Write failing selector/status tests**

Cover:
- Network status screen renders concise device/network basics
- Pi Stats renders temperature, load, memory, and disk summaries
- Logs screen renders recent lines for shell stack services with fallback if unavailable

Example target behaviors:

```python
def test_network_status_renders_operator_summary(): ...
def test_pi_stats_status_renders_system_summary(): ...
def test_logs_status_reads_shell_stack_services_with_fallback(): ...
```

**Step 2: Run the focused test file**

Run:

```bash
python -m pytest tests/test_boot_selector.py -q
```

Expected: missing content, placeholder-only assertions, or failing render expectations.

**Step 3: Implement read-only status providers**

Inside `boot/boot_selector.py`, add small shell-local helpers for:
- network summary gathering
- Pi stats summary gathering
- recent log retrieval for the shell stack services selected by the operator

Constraints:
- degrade gracefully when commands or data are unavailable
- never block shell startup on missing data
- keep rendering to the existing `stats.png`-based screen model

**Step 4: Wire status providers into the render path**

Replace placeholder text with concise operator-summary text blocks. Preserve strip-only back behavior.

**Step 5: Re-run the focused tests**

Run:

```bash
python -m pytest tests/test_boot_selector.py -q
```

Expected: Settings screen tests pass hardware-free.

**Step 6: Commit**

```bash
git add boot/boot_selector.py tests/test_boot_selector.py
git commit -m "feat: render operator summary content on settings screens"
```

---

### Task 6: Turn Themes into a generated picker that scales to 6 themes

**Owner:** Switchboard  
**Dependencies:** Task 2

**Files:**
- Modify: `boot/boot_selector.py`
- Test: `tests/test_boot_selector.py`

**Step 1: Write failing theme-grid tests**

Cover:
- discovered themes are not hardcoded to exactly three IDs
- up to 6 themes map to distinct touch targets on one screen
- selecting a theme persists and re-renders in place

Example target behaviors:

```python
def test_theme_picker_maps_each_discovered_theme_to_a_unique_zone(): ...
def test_theme_picker_supports_up_to_six_themes_without_paging(): ...
def test_theme_selection_persists_and_stays_on_themes_screen(): ...
```

**Step 2: Run the focused test file**

Run:

```bash
python -m pytest tests/test_boot_selector.py -q
```

Expected: failures around hardcoded three-column behavior.

**Step 3: Replace hardcoded three-theme mapping**

Refactor the current theme selection path so:
- theme IDs come from discovery
- touch zones are derived from the discovered order
- the picker supports 1 to 6 installed themes on a single screen

**Step 4: Generate or compose the picker background**

Because the user expects background rendering to change with installed themes, implement a shell-local generated picker surface instead of assuming fixed art encodes the only valid target map.

Constraints:
- keep this local to the selector
- do not add new dependencies
- do not add paging

**Step 5: Re-run the focused tests**

Run:

```bash
python -m pytest tests/test_boot_selector.py -q
```

Expected: unique mapping and persistence tests pass.

**Step 6: Commit**

```bash
git add boot/boot_selector.py tests/test_boot_selector.py
git commit -m "feat: generate a six-slot theme picker from discovered themes"
```

---

### Task 7: Harden regression coverage across Photos, Settings, and Themes

**Owner:** Sentinel  
**Dependencies:** Tasks 4, 5, 6

**Files:**
- Modify: `tests/test_boot_selector.py`
- Modify: `tests/test_photos.py`
- Modify: `coordination/status.md`

**Step 1: Add Photos interaction regression tests**

Assert:
- left/right navigation
- hold-to-exit
- no shell/child gesture conflict on the agreed path

**Step 2: Add Settings status regressions**

Assert:
- each status screen renders a stable, non-empty summary
- unavailable data produces an explicit fallback state instead of a crash

**Step 3: Add theme-grid regressions**

Assert:
- discovery order is stable
- 1 through 6 themes map deterministically
- theme apply stays on the Themes screen

**Step 4: Run targeted regression suites**

Run:

```bash
python -m pytest tests/test_boot_selector.py tests/test_photos.py -q
```

Expected: full pass.

**Step 5: Commit**

```bash
git add tests/test_boot_selector.py tests/test_photos.py coordination/status.md
git commit -m "test: cover photos settings and theme picker regressions"
```

---

### Task 8: Run hardware-free integration verification

**Owner:** Mouser  
**Dependencies:** Tasks 4, 5, 6, 7

**Files:**
- Modify: `coordination/status.md`
- Modify: `coordination/blockers.md`

**Step 1: Run the selector and Photos test suites**

Run:

```bash
python -m pytest tests/test_boot_selector.py tests/test_photos.py -q
```

Expected: PASS.

**Step 2: Run the shell integration checks that still matter**

Run:

```bash
python -m pytest tests/test_display_rotator.py -q
python -m py_compile boot/boot_selector.py modules/photos/slideshow.py modules/photos/display.py
```

Expected: PASS.

**Step 3: Record any residual blockers**

Only open blockers for:
- on-device-only behavior not reproducible locally
- asset/runtime contract mismatch
- unexpected shell-child ownership conflicts

**Step 4: Commit**

```bash
git add coordination/status.md coordination/blockers.md
git commit -m "docs: record integration verification for shell-owned app fixes"
```

---

### Task 9: Update operator-facing docs after behavior stabilizes

**Owner:** Curator  
**Dependencies:** Task 8

**Files:**
- Modify: `README.md`
- Modify: `coordination/status.md`

**Step 1: Document the margin controls**

Document the exact places to tune layout:
- global dashboard layout: `display_layout.py`
- shell status text layout: `boot/boot_selector.py`
- script-local offsets in Calendash, Currency, and Photos display helpers

**Step 2: Document Photos touch behavior**

Add the runtime contract:
- left tap previous
- right tap next
- hold exit

**Step 3: Document Settings and Themes behavior**

Add:
- operator-summary content expectations for Settings
- generated theme picker supporting up to 6 themes

**Step 4: Run a final documentation sanity pass**

Check that examples and paths match the implemented behavior exactly.

**Step 5: Commit**

```bash
git add README.md coordination/status.md
git commit -m "docs: describe shell-owned apps and layout controls"
```

---

## Acceptance Criteria

- Dashboard remains operational with no broad rebuild; margin tuning points are explicit and documented.
- Photos matches the requested dashboard-style touch contract.
- Settings shows real operator-summary content instead of placeholders.
- Themes supports up to 6 installed themes on one generated picker screen with deterministic touch mapping.
- Selector and Photos regression suites pass hardware-free.
- No systemd/timer changes and no shared framebuffer refactor are introduced.

## Risks and Controls

- **Risk:** Shell and Photos both consume the same gesture path.
  - **Control:** keep Photos child-owned while active and test hold-to-exit explicitly.
- **Risk:** Theme picker rendering becomes coupled to old fixed artwork.
  - **Control:** derive mapping from discovered themes and generate the selectable background locally.
- **Risk:** Settings content blocks or crashes on unavailable system data.
  - **Control:** implement read-only helpers with explicit fallback text and regression tests.

## Margin Reference

Use these files for layout tuning:

- Global dashboard spacing: `display_layout.py`
- Shell status-screen text positions: `boot/boot_selector.py`
- Calendash local vertical offset: `modules/calendash/calendash-api.py`
- Currency local content width: `modules/currency/currency-rate.py`
- Photos logo/crop tuning: `modules/photos/display.py`

Plan complete and saved to `docs/plans/2026-03-19-shell-owned-apps-and-layout-stabilization.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch a fresh subagent per implementation task, review between tasks, and integrate incrementally.

**2. Parallel Session (separate)** - Open a new session with executing-plans and execute the plan in a dedicated implementation pass.
