# Blockers

Live status: OPENED on 2026-03-19.

Rules:
- Any agent may log a blocker.
- Mouser decides resolution.
- Only Mouser may mark a blocker resolved.

---

## Current State

- No active blockers are recorded.

---

BLOCKER ID: B-001
Status: ACTIVE

Topic:
On-device Photos regression sign-off failure

Details:
- On host `pihole`, `python3 -m unittest tests.test_boot_selector tests.test_photos` fails in `tests.test_photos`.
- `test_touch_worker_emits_previous_next_and_menu_commands` patches `builtins.open` with `_FakeInputFile`, but `modules/photos/slideshow.py` uses `with open(...) as fd`, so the fake lacks the context-manager protocol and the worker exits before emitting events.
- `test_run_slideshow_rewinds_and_advances_with_touch_queue` patches the helper module loaded in the test as `photos_display`, but `modules/photos/slideshow.py` imports `display as photos_display`; the patch misses the live dependency used by `run_slideshow`, so the assertions do not observe the render/select calls they are meant to cover.

Impact:
- `R-019` regression hardening is not sign-off ready.
- Runtime smoke checks passed on host `pihole`, but the Photos regression layer cannot currently be trusted as evidence.

Next action requested:
- Sentinel should repair `tests/test_photos.py` so the on-device unittest baseline passes before integration is signed off.

## Logging Rule

Only log a blocker here if it is one of:
- a verified asset/path mismatch against the current theme or shell contract
- a shell-child touch ownership conflict that cannot be resolved within the approved file scope
- an on-device-only behavior gap that prevents local completion or sign-off
