# Active Plan: Themes, Back Stripe, and Settings Layout

Status: ACTIVE  
Date: 2026-03-28

This file supersedes the older shell-owned apps stabilization wording.

The active execution plan is this file. The older supporting document at `docs/plans/shell-owned-apps-plan.md` is now historical context and must not override this narrower slice.

## Active Goal

Finish the remaining shell work in `boot/boot_selector.py` so the Themes screen, shell back behavior, and Settings text layout are stable and easy to adjust on-device.

## In Scope

- Finish the remaining Themes selector fixes after the recent button-mapping correction work.
- Support operator replacement of `themes.png` when the final three-theme or four-theme layout is ready to deploy on the device.
- Move the shell back stripe to the right-hand side for better touch ergonomics.
- Correct Settings text rendering.
- Expose clearly marked code-only Settings layout constants in `boot/boot_selector.py` so the operator can manually tune text position, area, and font values later.
- Keep hardware-free validation current for the changed shell behavior.

## Out of Scope

- NASA app work is deferred to a separate slice after this plan is finished.
- No further Photos work in this slice.
- No Dashboard rebuild or broad rotator changes.
- No systemd or timer changes.
- No shared framebuffer refactor.
- No new dependencies without approval.
- No Settings UI for editing layout values.

## Runtime Contracts To Preserve

- `boot/boot_selector.py` remains the parent shell.
- `display_rotator.py` remains the dashboards child entrypoint.
- `modules/photos/slideshow.py` remains the Photos child entrypoint.
- Theme selection still persists through the existing shell theme state path.
- Settings remains a shell-owned screen, not a child app.

## Known Inconsistencies

- The device checkout at `/home/pihole/zero2dash` is still on the older control-plane wording in `PLAN.md`, `AGENTS.md`, and `coordination/*`.
- Local coordination files were previously still describing already-completed or superseded workstreams instead of only the remaining slice.

These do not block code changes in `boot/boot_selector.py`, but they do block clean progress tracking and device/local sign-off until they are aligned.

## Missing Information To Confirm During Execution

- Exact deployed `themes.png` replacement procedure on the device.
- Whether the final target layout is three themes, four themes, or both depending on installed theme count.
- Exact right-side back stripe width that feels best on-device.
- Exact Settings screens covered by the layout constants if more than one shell status screen shares the same renderer.
- Final font asset and default font size to expose as the operator-tunable baseline.

Verified device facts:
- the device repo is clean on `main` at `f7f2a71`
- the actual theme directories present on both device and local repo are `carbon`, `comic`, `frosty`, and `steele`
- `boot/boot_selector.py` on device already contains theme discovery and theme picker routing helpers, so the remaining work is refinement rather than first introduction
- `boot/boot_selector.py` still routes shell back behavior through the left strip using `screen_x < MENU_STRIP_WIDTH`
- Settings layout currently exposes only `STATUS_TITLE_X`, `STATUS_TITLE_Y`, `STATUS_BODY_X`, `STATUS_BODY_Y`, `STATUS_LINE_SPACING`, and `STATUS_WRAP_WIDTH`, and still hardcodes `ImageFont.load_default()`
- no checked-in `tests/test_boot_selector.py` source file currently exists in either the local repo or the device checkout

Work may begin before all of these are finalized, but any unresolved item must be called out in progress updates and validation notes.

## Segments

### Segment 1: Contract And Tracking Reset

Status: OPEN

Goal:
- Align the control plane so progress can be checked step by step without stale NASA or Photos scope leaking back in.

Files:
- `PLAN.md`
- `coordination/tasks.md`
- `coordination/status.md`
- `coordination/decisions.md`
- optionally `AGENTS.md` if the repo-level source of truth is being corrected in this slice

Tasks:
- Record this narrower slice as the active one.
- Remove completed Photos work from active task tracking.
- Add explicit progress checkpoints for the remaining shell work.
- Record any unresolved operator decisions as assumptions or blockers.

Acceptance:
- Every active task maps to remaining work only.
- No active tracker claims Photos is still part of this slice.
- The current plan is the clear source of truth for execution order.

### Segment 2: Themes Finalization

Status: OPEN

Goal:
- Finish the remaining Themes behavior around discovered theme count, touch targets, and operator-managed selector artwork.

Files:
- `boot/boot_selector.py`
- `tests/test_boot_selector.py`
- `coordination/status.md`

Tasks:
- Verify the current theme discovery order and target mapping.
- Confirm that the recent button-assignment fix did not leave any stale zone logic behind.
- Finalize selector behavior for the intended three-theme and/or four-theme device layout.
- Keep the code compatible with operator replacement of `themes.png`.
- Record whether any final artwork deployment step is required on the device.

Acceptance:
- Each visible Themes touch target selects the intended theme.
- No inactive or mismapped theme zone remains in the live layout.
- The code does not assume exactly three themes unless that is the explicitly chosen final contract.
- The required `themes.png` follow-up is clearly documented as either done, pending deployment, or no longer needed.

### Segment 3: Right-Side Back Stripe

Status: OPEN

Goal:
- Move the shell back stripe from the left side to the right side without breaking other shell routing.

Files:
- `boot/boot_selector.py`
- `tests/test_boot_selector.py`
- `coordination/status.md`

Tasks:
- Identify the current strip-hit logic and move it to the right edge.
- Preserve existing non-back touch behavior everywhere else.
- Confirm whether all shell-owned screens use the same strip rule or whether the Themes/Settings screens differ.
- Add or update regression coverage for the new strip position.

Acceptance:
- Back/exit stripe is on the right-hand side on the affected shell screens.
- Non-strip taps still route to the intended actions.
- Touch logic remains deterministic and hardware-free tests cover the new edge behavior.

### Segment 4: Settings Layout Stabilization

Status: OPEN

Goal:
- Fix incorrect Settings text rendering and make future hand-tuning straightforward in code.

Files:
- `boot/boot_selector.py`
- `tests/test_boot_selector.py`
- `coordination/status.md`

Tasks:
- Correct the current Settings text placement and readability issues.
- Extract or highlight the Settings layout values near the render logic or in a clearly labeled constant block.
- Make the following values easy to change by hand:
  - text x position
  - text y position
  - text area width and height
  - font path or font choice
  - font size
- Add a brief code comment that tells the operator these are the values to edit for manual layout tuning.

Acceptance:
- Settings text renders correctly in the current layout.
- The layout-tuning values are obvious in code and do not require hunting through render math.
- No Settings UI control is added for layout editing.

### Segment 5: Validation And Closeout

Status: OPEN

Goal:
- Verify the remaining shell slice and leave a clean progress record.

Files:
- `tests/test_boot_selector.py`
- `coordination/status.md`
- `coordination/blockers.md`
- `README.md` if operator-facing notes are updated in this slice

Tasks:
- Run focused hardware-free validation for the changed shell behavior.
- Record what was validated locally versus what still requires device confirmation.
- Record any pending operator action such as uploading a final `themes.png`.
- Close only the segments that have direct evidence.

Acceptance:
- Validation status is explicit for Themes, right-side back stripe, and Settings layout.
- Any device-only step is recorded as pending rather than implied complete.
- Progress tracking shows each segment as open, in progress, blocked, or complete.

## Execution Order

1. Segment 1: Contract and tracking reset
2. Segment 2: Themes finalization
3. Segment 3: Right-side back stripe
4. Segment 4: Settings layout stabilization
5. Segment 5: Validation and closeout

Segments 2, 3, and 4 all touch `boot/boot_selector.py`, so they should be implemented serially, not in parallel.

## Progress Rules

- Start a segment only after its goal, files, and acceptance checks are understood.
- Update coordination after each segment changes state.
- Mark a segment COMPLETE only with direct evidence:
  - code landed
  - tests passed or device behavior confirmed
  - pending manual device steps explicitly recorded
- If device behavior contradicts local validation, device behavior wins and the segment reopens.

## Definition Of Done

This slice is done when:

- Themes behavior matches the intended live button layout.
- The operator knows whether a new `themes.png` must still be uploaded to the device.
- The shell back stripe is on the right-hand side where intended.
- Settings text renders acceptably.
- The code clearly shows which Settings constants to edit for manual position, size, and font tuning.
- Active progress records match reality and no stale NASA or completed Photos slice remains in the live execution story.
