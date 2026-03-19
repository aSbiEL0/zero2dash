# Blockers

This file tracks issues preventing progress in the current run.
`PLAN.md` remains the only execution source of truth.

Rules:
- Any agent may log a blocker.
- Mouser decides resolution.
- Only Mouser may mark a blocker resolved.
- Archive blocker entries from previous teams are historical only.

---

## Blocker Template

BLOCKER ID: B-XXX
Raised by:
Status: OPEN | RESOLVED

Problem:
<clear description>

Impact:
- affected tasks
- affected agents

Possible cause:
<optional>

Suggested resolution:
<optional>

Notes:
<optional>

---

## Active Blockers

BLOCKER ID: B-001
Raised by: Mouser
Status: RESOLVED

Problem:
Committed merge-conflict markers currently break `display_rotator.py`, `display_layout.py`, and `modules/trams/display.py`.

Impact:
- blocks `R-010` validation
- blocks clean dashboards runtime execution
- increases risk for `R-011` because the shell rewrite depends on a working dashboards child

Possible cause:
An incomplete merge landed both legacy inline rotator code and extracted module code in the same files.

Suggested resolution:
Resolve the conflict residue in the Rotor stream first and preserve the extracted `rotator/*` architecture while restoring the `MAIN_MENU` long-press contract.

Notes:
Resolved by the Rotor stream on 2026-03-19. The files are conflict-free again and hardware-free verification passed.

No open software blockers remain in the current run. Remaining validation is hardware-side Pi verification.

BLOCKER ID: B-002
Raised by: Mouser
Status: RESOLVED

Problem:
The separate GitHub wiki repository had not been verified for remote publication.

Impact:
- previously blocked claiming remote wiki deployment readiness

Possible cause:
Initial Curator status was based on an outdated assumption about wiki remote access.

Suggested resolution:
None. The wiki remote was verified and cloned successfully.

Notes:
Remote publication is no longer blocked by access. It is intentionally held until Pi smoke confirmation finishes.

BLOCKER ID: B-003
Raised by: Mouser
Status: OPEN

Problem:
Pi smoke testing has cleared the shell startup blockers, but the remaining live interaction defects still block sign-off: root-menu touch mapping is wrong, Dashboard freezes touch, Dashboard/Night child readers still miss ADS7846 events, and keypad confirm/cancel hit testing is not aligned to the asset.

Impact:
- blocks closing Pi validation
- blocks final wiki publication, because runtime confirmation on device is still incomplete

Possible cause:
Likely causes are:
- touch probe is auto-selecting the wrong `/dev/input/event*` device
- the service user cannot read the chosen input device
- `touch_calibration.py` is bound to the wrong event device and is remapping coordinates incorrectly
- the shell reader only emitted taps from `BTN_TOUCH` or multitouch tracking IDs, while the Pi probe selected an `ADS7846 Touchscreen` that reports `BTN_TOUCH=no`
- `main_menu_1` currently launches Dashboard directly instead of routing through `dashboards_menu`
- the shell and Dashboard/Night child readers can compete for the same touch device

Suggested resolution:
Capture the touch probe result on the Pi, then confirm device permissions and calibration binding:
- `/usr/bin/python3 -u boot/boot_selector.py --probe-touch`
- `ls -l /dev/input/event*`
- `grep -E 'TOUCH_DEVICE|ROTATOR_TOUCH_DEVICE' /etc/systemd/system/boot-selector.service /etc/systemd/system/boot-selector.service.d/* 2>/dev/null`
If probe selects the wrong device, force the correct one with `TOUCH_DEVICE=/dev/input/eventX`.
If the probe is correct and the device is `ADS7846`, deploy the selector patch that accepts `ABS_X/ABS_Y + EV_SYN` samples as taps when no explicit touch-state events are present.
Then repair the runtime contract so:
- root Dashboards opens `dashboards_menu`
- Dashboard/Night children request `menu` from the running shell instead of starting another selector
- calibration can be regenerated and applied consistently across shell/keypad/child apps
- use `python3 boot/boot_selector.py --calibrate-touch` on the Pi if zone mapping is still wrong after the runtime fix

Notes:
This remains the active Pi validation blocker. The shell itself boots to the main menu successfully after the startup fixes, but runtime interaction is still not trustworthy enough to close the slice.
Latest Pi probe:
- selected `/dev/input/event0`
- name `ADS7846 Touchscreen`
- `BTN_TOUCH=no`
Latest Pi crash evidence:
- `display_rotator.py` exited with `TypeError: discover_pages() got an unexpected keyword argument 'resolve_path'`
- `modules/blackout/blackout.py` exited with `ModuleNotFoundError: No module named 'framebuffer'`
Latest Pi keypad evidence:
- Dashboard child now launches successfully
- `pin_keypad` still misroutes taps because the current selector logic assumes a 3x4 keypad with bottom-row cancel/0/ok, but the real asset is a 4x3 grid with `ok` top-right, `0` middle-right, and `cancel` bottom-right
- failed PIN streaks were also persisting across unrelated menu navigation, which made the third-failure shutdown trigger after non-consecutive attempts
Latest repo note:
- the remediation code is now in place locally
- the child-app crash fixes are now in place locally and await Pi retest
- the keypad layout fix is now in place locally and awaits Pi retest
- the PIN streak reset fix is now in place locally and awaits Pi retest
- local Python test execution is currently blocked in this shell by a wrapper/interpreter issue, so Pi validation is the next gate
