# Architecture Decisions

Live status: RESET on 2026-03-28.

Rules:
- Mouser or the operator records decisions.
- Recorded entries clarify execution within `PLAN.md`; they do not replace it.

---

DECISION ID: D-022
Status: ACTIVE

Topic:
Active shell slice scope

Decision:
Treat Themes finalization, right-side back stripe behavior, and Settings layout stabilization as the only active implementation scope.

Reason:
The operator confirmed Photos work is complete for now, and NASA app work will be handled in a later separate slice.

Implications:
- do not reopen Photos implementation in this slice
- do not treat NASA app work as current priority
- keep `boot/boot_selector.py` as the main implementation surface

Supersedes:
- older Photos/NASA-oriented active-slice wording

---

DECISION ID: D-023
Status: ACTIVE

Topic:
Theme inventory source of truth

Decision:
Use the actual discovered theme ids from the filesystem and `--dump-contracts` output as the source of truth for theme mapping.

Reason:
Verified code inspection showed that the live theme ids are `carbon`, `comic`, `frosty`, and `steele`, while fixed preferred-order ids in code still reference `brushed_steel` and `comic_book`.

Implications:
- remaining Themes work must reconcile fixed button order with real theme ids
- progress tracking must stop referring to stale ids such as `default`
- the current issue is a code/id mismatch, not a missing theme discovery system

Supersedes:
- stale coordination references to `default` as an installed theme

---

DECISION ID: D-024
Status: ACTIVE

Topic:
Back stripe ergonomics

Decision:
Move the shell back stripe from the left-hand side to the right-hand side on the affected shell screens.

Reason:
The operator reported that the right edge is more ergonomic during actual device use, and code inspection verified that routing is still left-sided today.

Implications:
- update `resolve_screen_action()` and any dependent routing assumptions
- preserve non-strip tap behavior everywhere else
- validate right-edge behavior explicitly after the change

Supersedes:
- previous left-strip shell behavior for this slice

---

DECISION ID: D-025
Status: ACTIVE

Topic:
Settings layout tuning model

Decision:
Settings layout tuning remains code-only and must expose clear hand-editable values for position, area, and font controls.

Reason:
The operator wants to adjust layout manually in code, not through a UI, and current code inspection shows only partial layout controls are exposed today.

Implications:
- keep the tuning surface in `boot/boot_selector.py`
- expose font choice or path and font size alongside positional constants
- add a short comment showing what to edit for manual tuning
- do not add layout controls to the interface

Supersedes:
- any ambiguous interpretation that a UI editor might be added

---

DECISION ID: D-026
Status: ACTIVE

Topic:
Regression evidence baseline

Decision:
Do not assume checked-in regression source files exist; verify the test surface before promising shell regression coverage updates.

Reason:
Actual filesystem inspection on both local and device showed no checked-in `tests/test_boot_selector.py` source file, only compiled cache artifacts.

Implications:
- validation planning must account for absent test sources
- if regression coverage is required, test source files may need to be restored or created first
- progress reports must distinguish code inspection from executable regression evidence

Supersedes:
- older coordination entries that assumed `tests/test_boot_selector.py` already existed as a source file
