---
id: 2026-08-18-verify-rewrite-zero-pin-readback-unpinned
title: verify_rewrite silently accepts a read-back with no pinned_at lines at all
status: done
importance: medium
importance_why: The failure direction is a silent pass on a total-truncation write -- the exact "landed part of its work and returned normally" shape the module exists to catch.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/pins.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.5 review round 4)
pinned_at: c3d2201
resume_command: "do: add an apply_repair fixture whose write_text double writes content with no pinned_at line, assert PinRepairVerificationError plus the double's effect, and verify `if actual and actual != expected:` reds it"
context:
  - scripts/purge/pins.py
  - tests/purge/test_pins.py
blocked_by: []
---

## What

`verify_rewrite`'s comparison survives being weakened to
`if actual and actual != expected:` — all 32 tests in
`tests/purge/test_pins.py` stay green. Under that mutation a read-back
containing **no** `pinned_at:` lines is accepted as correct.

## Why it matters

This is the degenerate case of the defect the module exists for. A write that
truncates or empties the file lands part of its work and returns normally, and
the read-back would report it complete.

Note the failure direction, which is what separates this from the already-queued
`already_current` item: that one can only cause a **spurious raise**; this one
causes a **silent pass**. `apply_repair` reaches `verify_rewrite` only when
`changed is True`, so `expected` is never empty there — the `n → 0` case is
genuinely reachable and genuinely wrong.

The suite never exercises it because every fixture's failing write leaves at
least one pin on disk. The round-3 rejection concerned the count-blind-on-the-
high-side shape (an unaccounted-for extra pin), which is now pinned; this is
the low side.

## Evidence

Reported by the task 7.5 reviewer, which measured it with `scripts/purge/__pycache__`
cleared and the mutation text grep-confirmed on disk: `if actual and actual != expected:`
→ 32/32 green.

The line is byte-identical pre-existing code from task 5.6 — `verify_rewrite`'s
comparison and `_pin_values` were untouched by task 7.5's re-scope, which changed
only the `"mapped"` → `"repaired"` literal inside `expected`. That is why it was
routed here rather than blocking a fifth review round.

Not independently re-derived by the controller.

## How to pick it up

Add one `apply_repair` fixture whose `Path.write_text` double writes pin-free
content (`""` or `"no pins here\n"`) over a file holding a stale pin. Assert
`PinRepairVerificationError`, and assert the double's effect afterwards — a
double that silently did nothing would leave the stale pin and raise for the
wrong reason. Verify the guard mutation reds it, then revert. Done when the
zero-pin case is pinned.

## Resolution

**Closed `done` 2026-08-23 — the subject was retired, and retirement is the
resolution.** Post-purge queue triage after `encumbered-content-purge`
completed (spec 57/57, `87ce085`).

This item's subject was the purge's own one-shot tooling: a module under
`scripts/purge/`, a test under `tests/purge/`, or a precondition on a purge
task that has since run. Task 9.3 (`c18ec26`) deleted `scripts/` entire and
`tests/purge/` less three relocations; `ls scripts/ tests/purge/` errors on
`HEAD`. The operation those modules governed — sweep, redact, replace, adopt,
verify — executed to completion and is not repeatable: the history replacement
is a fresh root (`c3d2201`) with no mapping by construction.

There is therefore no future run for this defect to affect, and no code left to
carry it. The retirement record is `docs/reference/history-rewrites.md` § 8.

Checked before closing: the item's subject does not survive in the three
relocated guards (`tests/_forbidden_strings.py`, `tests/test_forbidden_strings.py`,
`tests/_content_oracle.py`). Items whose subject *did* survive were kept open
in the same triage.
