---
id: 2026-07-26-store-profileerror-paths-undocumented
title: The profile store's new ProfileError paths are undocumented on with_benchmark and their refusal message is unpinned
status: open
importance: medium
importance_why: A caller catching only ValueError per the documented contract will crash; the refusal message is the sole thing making the failure actionable and nothing asserts its content.
effort: S
kind: gap
area: athlete-benchmarks, src/fitdocs/load/profile.py, tests/load/test_profile.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 3.2, rounds 4-5 review)
pinned_at: c3d2201
resume_command: "/kiro-impl athlete-benchmarks [queue: .kiro/queue/2026-07-26-store-profileerror-paths-undocumented.md] Document with_benchmark's ProfileError path and pin the save refusal message"
context:
  - .kiro/specs/athlete-benchmarks/design.md
  - src/fitdocs/load/profile.py
  - tests/load/test_profile.py
blocked_by: []
---

## What
Task 3.2 gave the store two new failure paths that raise `ProfileError`:

1. `_canonicalize_benchmarks_region` refuses an unmergeable collision across two
   scope spellings (`src/fitdocs/load/profile.py:502`). This is reachable from
   **`with_benchmark`**, not only `save_profile` — but `with_benchmark`'s
   docstring and design.md's `#### BenchmarkStore` preconditions both document
   only `ValueError`, and all three refusal tests drive it through
   `save_profile`.
2. `save_profile` re-parses the assembled document before the atomic rename and
   refuses rather than writing (`:376-377`). Its message content is asserted by
   nothing.

## Why it matters
On (1), the documented contract is wrong in a way that produces a crash rather
than a handled error: a caller following the docstring catches `ValueError` and
is broken by a `ProfileError`, which subclasses `AthleteFileError`, not
`ValueError`. The prompt flow (task 4.2) is the imminent caller.

On (2), the reviewer chain accepted the refusal as the right trade over silent
data loss **specifically because the message is actionable** — it names the
target file and the underlying `BenchmarkError`. That justification rests
entirely on message content that no test pins, and its sibling message (the
collision refusal) *was* pinned with a `match=` in round 5, so the asymmetry is
accidental rather than considered.

## Evidence
At `84e5e56`:
- `src/fitdocs/load/profile.py:502` — `raise ProfileError(...)` inside
  `_canonicalize_benchmarks_region`, which `with_benchmark` reaches via
  `_merge_benchmarks_document`
- `src/fitdocs/load/profile.py:376-377` — `raise ProfileError(f"refusing to
  write {target}: the assembled document would not ...")`

Reported by the round-4 and closing reviewer subagents of task 3.2, which
reproduced the `with_benchmark` route directly. The message-unpinned claim was
verified by mutation by the closing reviewer: replacing the f-string at `:377`
with a bare literal `"refusing to write the profile"` leaves the suite green at
1991, cache-cleared. Not re-reproduced in the session filing this item.

Note the docstring claim at `:355-357` — that the rejection names the target and
the underlying `BenchmarkError` — is **true** of the shipped code; this is an
unpinned truth, not a false claim.

## How to pick it up
Open `src/fitdocs/load/profile.py` and read `with_benchmark`'s docstring
(~`:224-262`) against the call chain into `_canonicalize_benchmarks_region`.
Add the `ProfileError` path to that docstring and to design.md's
`#### BenchmarkStore` preconditions, and add one test that reaches it **through
`with_benchmark`** rather than `save_profile`.

Then add `match=` to the existing `pytest.raises(ProfileError)` for the
re-parse refusal in `tests/load/test_profile.py` (the hand-forged
duplicate-`BenchmarkSet` test), asserting the target path and the underlying
error text appear.

Done when: both mutations red — the f-string → bare literal at `:377`, and
deleting the newly documented `with_benchmark` path's coverage. Verify
cache-cleared per `2026-07-26-pycache-masks-length-preserving-mutations`.
