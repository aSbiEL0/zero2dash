# Upgrade Plan: Pi Shell + Dashboards App Split, Parallelised for Multi-Agent Delivery

  ## Summary

  Refactor the current boot selector into a long-running shell that owns startup, navigation, app lifecycle, and shell-
  global gestures. Keep display_rotator.py as the Dashboards app. Split Photos out of dashboard rotation into a
  dedicated slideshow app wrapper. Preserve background refresh jobs. Preserve day/night scheduling, but retarget timers
  to switch shell mode rather than swapping foreground services.

  This plan is structured for parallel implementation. Each workstream has:

  - a clear owner boundary
  - explicit inputs/outputs
  - dependency labels
  - merge-safe sequencing

  Chosen defaults:

  - Photos becomes an auto-advancing slideshow app.
  - day.timer / night.timer remain, but trigger shell mode changes.
  - The shell is the only normal foreground owner of /dev/fb1.
  - display.service and night.service remain compatibility/manual paths during transition only.

  ## Delivery Structure

  ### Stream A: Shell Runtime

  Status: foundational
  Can start immediately.

  Goals:

  - Turn boot/boot_selector.py into a persistent shell state machine.
  - Add app registry, app runner, paged menu, and shell-global Home gesture.
  - Support shell-owned screens and subprocess-backed apps.

  Outputs:

  - Long-running shell loop
  - AppSpec registry
  - shell state model
  - child process lifecycle management
  - paged 4-tile menu
  - shell Home long-press reclaim

  Dependencies:

  - none to start
  - consumes Stream C app commands once available
  - consumes Stream D timer trigger interface once defined

  ### Stream B: Dashboards App

  Status: parallel after contract lock
  Can start immediately once shell app contract is frozen.

  Goals:

  - Keep display_rotator.py as a standalone app.
  - Remove photos from modules.txt.
  - Add per-module dwell override metadata.

  Outputs:

  - dashboard-only rotation list
  - module metadata loader
  - per-module dwell override support
  - unchanged touch next/previous, quarantine, and backoff behaviour

  Dependencies:

  - none for internal work
  - only needs Stream A to launch it from shell
  - documentation sync with Stream E

  ### Stream C: Photos App

  Status: parallel after shell app lifecycle contract
  Can start once Stream A publishes child-app launch/stop contract.

  Goals:

  - Build a long-running slideshow wrapper around current photos rendering logic.
  - Keep existing local/online/cache/fallback selection behaviour.
  - Make it shell-launchable and shell-stoppable.

  Outputs:

  - dedicated Photos app entrypoint
  - slideshow loop with timed advance
  - clean termination handling
  - no local exit UI; shell Home gesture remains global exit path

  Dependencies:

  - depends on Stream A for app process contract
  - can reuse current module logic without waiting for Stream B

  ### Stream D: systemd / Ops Transition

  Status: gated
  Should begin after Stream A shell mode interface is stable.

  Goals:

  - Make the shell the primary foreground runtime.
  - Retarget day/night timers to request shell mode changes.
  - Preserve refresh timers/services unchanged.

  Outputs:

  - updated boot-selector.service
  - new shell mode-switch mechanism
  - retargeted day.timer / night.timer
  - compatibility status for display.service / night.service

  Dependencies:

  - depends on Stream A exposing a concrete shell mode-switch entrypoint
  - should not merge before Stream A is functionally testable

  ### Stream E: Docs / Migration / Validation

  Status: parallel, but final pass last
  Can start early for skeleton docs; final merge after A-D.

  Goals:

  - Update README, AGENTS docs, and operator guidance.
  - Document shell-first runtime, Dashboards app, Photos app, timer retargeting, and compatibility paths.
  - Provide migration and acceptance checklist.

  Outputs:

  - updated runtime docs
  - operator migration steps
  - validation commands and smoke-test guidance

  Dependencies:

  - consumes final behaviour from Streams A-D
  - should do final sweep after code streams merge

  ## Shared Contracts To Lock First

  These are the only items that must be agreed early to avoid parallel work colliding.

  ### Contract 1: Shell App Registry

  Owned by Stream A.
  Consumed by Streams C, D, E.

  Required shape:

  - id
  - label
  - menu_page
  - tile_index
  - kind
  - launch_command
  - preview_asset
  - supports_home_gesture

  Fixed v1 app set:

  - Dashboards
  - Photos
  - Info GIF
  - Keypad
  - Shutdown

  ### Contract 2: Shell App Lifecycle

  Owned by Stream A.
  Consumed by Streams B and C.

  Required behaviour:

  - start child app
  - stop child app gracefully, then force-kill if needed
  - detect running child
  - reclaim control on Home long-press
  - return to shell menu cleanly

  ### Contract 3: Shell Mode Switching

  Owned by Stream A, implemented with Stream D.

  Required modes:

  - menu
  - dashboards
  - photos
  - night

  Required interface:

  - one concrete shell-targeted mode-switch trigger usable by timer-driven oneshot units or equivalent command path

  ### Contract 4: Dashboard Module Metadata

  Owned by Stream B.
  Consumed by Stream E.

  Required v1 metadata:

  - optional dwell_secs

  Rules:

  - absent metadata -> use ROTATOR_SECS
  - invalid metadata -> log and fall back
  - no extra module behaviour in v1

  ## Step-by-Step Execution Plan

  ### Phase 1: Contract Lock and Spine

  Owner grouping:

  - Stream A primary
  - Stream E optional skeleton docs

  Steps:

  1. Refactor boot_selector.py into a shell-oriented structure without changing visible behaviour yet.
  2. Introduce shell states:
      - boot_gif
      - main_menu
      - day_night_menu
      - keypad
      - shutdown_confirm
      - running_app
  3. Add the AppSpec registry and child-app runner abstraction.
  4. Replace direct systemctl start UI launches with internal app-launch hooks.
  5. Define the shell mode-switch interface for later timer integration.

  Parallelism:

  - Stream B can begin rotator metadata work after the shell launch contract is published.
  - Stream C can begin slideshow wrapper once the child-app contract is published.
  - Stream D waits for the mode-switch interface.
  - Stream E can draft updated architecture docs.

  ### Phase 2: App Separation

  Owner grouping:

  - Stream B
  - Stream C

  Steps:

  1. Stream B removes photos from modules.txt.
  2. Stream B adds per-module dwell metadata support to display_rotator.py.
  3. Stream B keeps all existing rotator behaviour otherwise stable.
  4. Stream C builds a dedicated photos slideshow app wrapper.
  5. Stream C reuses current photos config, selection, auth, cache, and fallback logic.
  6. Stream C adds clean signal handling and shell-controlled exit.

  Parallelism:

  - Streams B and C should not edit the same files except docs or shared imports.
  - They can merge independently once Stream A app-launch contract is stable.

  ### Phase 3: Shell UX Completion

  Owner grouping:

  - Stream A
  - Stream C for real app hookup

  Steps:

  1. Replace fixed 4-quadrant menu flow with a paged 4-tile shell menu.
  2. Wire registry entries for Dashboards and Photos subprocess apps.
  3. Preserve shell-owned Info GIF, keypad, and shutdown screens.
  4. Add reserved-corner long-press Home gesture that always overrides child app control.
  5. Ensure the shell can stop Dashboards, Photos, or Night app and redraw its own menu reliably.

  Parallelism:

  - Stream A can integrate Stream B and C outputs separately.
  - No dependency on Stream D yet.

  ### Phase 4: systemd Transition

  Owner grouping:

  - Stream D
  - Stream A support

  Steps:

  1. Make boot-selector.service the primary foreground UI service.
  2. Keep current refresh services/timers unchanged.
  3. Retarget day.timer / night.timer to shell mode-switch actions.
  4. Keep display.service / night.service as compatibility/manual paths only during migration.
  5. Ensure no normal runtime path leaves multiple foreground services competing for framebuffer ownership.

  Parallelism:

  - Mostly isolated to systemd/ and shell mode-switch glue.
  - Should merge after shell mode switching is verified locally.

  ### Phase 5: Hardening and Docs

  Owner grouping:

  - Stream E
  - all streams contribute acceptance notes

  Steps:

  1. Update README and AGENTS docs for shell-first architecture.
  2. Document Photos as a top-level app, not a dashboard page.
  3. Document dashboard module dwell metadata.
  4. Document timer retargeting and compatibility/manual services.
  5. Add operator migration instructions and smoke checks.

  Parallelism:

  - Can be prepared incrementally.
  - Final pass should happen after Streams A-D are merged.

  ## Multi-Agent Work Allocation

  ### Agent 1: Shell Agent

  Scope:

  - boot/boot_selector.py
  - shell registry
  - app runner
  - menu paging
  - Home gesture
  - shell mode interface

  Must not do:

  - rotator dwell metadata
  - photos slideshow internals
  - systemd unit rewiring beyond interface notes

  ### Agent 2: Dashboards Agent

  Scope:

  - display_rotator.py
  - modules.txt
  - module metadata reading
  - dwell override behaviour
  - rotator tests

  Must not do:

  - shell lifecycle logic
  - photos app loop
  - timer rewiring

  ### Agent 3: Photos Agent

  Scope:

  - dedicated slideshow wrapper
  - reuse/extract logic from modules/photos/display.py
  - slideshow timing
  - clean app termination
  - photos tests

  Must not do:

  - shell gesture logic
  - rotator changes
  - systemd wiring

  ### Agent 4: Ops Agent

  Scope:

  - systemd/
  - shell mode-switch oneshot/service design
  - compatibility service strategy
  - service/timer migration docs

  Must not do:

  - UI behaviour changes inside shell
  - rotator behaviour changes
  - photos slideshow logic

  ### Agent 5: Docs/QA Agent

  Scope:

  - README
  - AGENTS docs
  - migration notes
  - validation matrix
  - cross-stream acceptance checklist

  Must not do:

  - invent runtime behaviour not already implemented

  ## Integration Order

  1. Stream A contract branch merges first.
  2. Streams B and C merge independently after A contract lock.
  3. Stream A integration pass wires B and C outputs into the menu.
  4. Stream D merges after shell mode-switch path is stable.
  5. Stream E finalises docs and validation after A-D.

  ## Test Plan

  - Shell startup:
      - paged menu works across multiple pages
      - Dashboards launches and exits back to shell
      - Photos launches and exits back to shell
      - Home long-press reliably reclaims control
      - no orphan child processes remain
  - Dashboards:
      - photos removed without breaking discovery
      - default dwell applies when no metadata exists
      - per-module dwell_secs override works
      - next/previous touch still works
      - backoff/quarantine still work
  - Photos:
      - slideshow advances automatically
      - local source works
      - online source works if configured
      - offline cache fallback works
      - fallback image works
  - systemd:
      - shell is the normal foreground runtime
      - day.timer / night.timer switch shell modes rather than starting competing UI services
      - refresh timers remain unaffected
  - Regression:
      - touch probing still works
      - info GIF, keypad, shutdown, and blackout behaviour remain intact

  ## Assumptions

  - Home gesture is a reserved-corner long-press and is the only shell-global touch override while an app runs.
  - Photos v1 is an auto slideshow, not a manual browser.
  - Night mode remains implemented via the existing blackout script in v1.
  - Background refresh remains decoupled from foreground UI.
  - The plan prioritises merge-safe parallelism over large architectural rewrites.

