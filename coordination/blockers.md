# Blockers

Live status: RESET on 2026-03-28.

Rules:
- Any agent may log a blocker.
- Mouser decides resolution.
- Only Mouser may mark a blocker resolved.

---

## Current State

- One active blocker is recorded.

---

BLOCKER ID: B-002
Status: RESOLVED

Topic:
Theme button order ids do not match live theme ids

Details:
- Verified in `boot/boot_selector.py`, `THEME_BUTTON_ORDER` is currently:
  - `carbon`
  - `brushed_steel`
  - `comic_book`
  - `frosty`
- Verified from filesystem and `--dump-contracts`, the actual live/discovered theme ids are:
  - `carbon`
  - `comic`
  - `frosty`
  - `steele`

Impact:
- Fixed preferred button assignments could not map cleanly to the intended live themes.
- This directly affected the remaining Themes selector correctness work.

Workaround:
- None was trustworthy enough for sign-off; the code ids needed to be reconciled.

Unblock condition:
- Theme ordering and touch-target logic use the real live ids or an explicit mapping layer that matches the actual installed themes.

Resolution:
- Local `boot/boot_selector.py` now sets `THEME_BUTTON_ORDER` to `carbon`, `steele`, `comic`, `frosty`, which preserves the working assignments and swaps only `steele` and `frosty` as requested.

---

BLOCKER ID: B-003
Status: ACTIVE

Topic:
Regression source files for shell validation are missing

Details:
- No checked-in `tests/test_boot_selector.py` source file exists locally or on the device.
- Filesystem inspection found only compiled `__pycache__` artifacts for the test module names.

Impact:
- The current plan cannot honestly claim focused shell regression updates until the test source situation is resolved.
- Validation is limited to code inspection and runtime checks unless new or restored test sources are provided.

Workaround:
- Use code inspection and targeted runtime commands for interim verification.

Unblock condition:
- Restore or create the required checked-in test source files, or explicitly narrow validation expectations away from source-level regression edits.

## Logging Rule

Only log a blocker here if it is one of:
- a verified asset/path mismatch against the current shell contract
- a code-level routing or contract mismatch that blocks sign-off
- a missing validation surface that prevents credible completion claims
