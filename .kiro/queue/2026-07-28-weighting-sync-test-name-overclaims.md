---
id: 2026-07-28-weighting-sync-test-name-overclaims
title: test_the_four_weighting_terms_bound_values_match_stress_py checks only two of the four
status: open
importance: low
importance_why: The name asserts coverage the body does not have, so a later session reading the test list believes the female curve is pinned against a module when nothing ships it yet.
effort: S
kind: coverage-gap
area: fit-ingest, tests/metrics/test_sources.py
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 9.3 verification pass)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest 12.2 [queue: .kiro/queue/2026-07-28-weighting-sync-test-name-overclaims.md] Rename or extend the weighting module-sync test so its name matches what it checks"
context:
  - tests/metrics/test_sources.py
  - src/fitdocs/metrics/stress.py
  - src/fitdocs/metrics/sources.py
blocked_by: []
---

## What

`test_the_four_weighting_terms_bound_values_match_stress_py`
(`tests/metrics/test_sources.py:1364`) is named for four terms and checks two.
`stress.py` ships only the male curve — `_TRIMP_COEFFICIENT` (0.64) and
`_TRIMP_EXPONENT` (1.92) — so the female pair (0.86 / 1.67) has no module
constant to compare against and the test body cannot check it.

The body is correct for what it can reach. The *name* is the defect: it states
coverage that does not exist.

## Why it matters

Test names are how a later session decides what is already pinned. This one
reads as "all four weighting terms are verified against the shipping module",
which is what a session touching `stress.py` in task 11 or 12.2 would rely on.
In fact the two female values are pinned only as literals inside
`sources.py` and its backstops — nothing checks them against arithmetic,
because no arithmetic uses them yet.

Low importance because the female curve is genuinely unreachable until task 11
threads the weighting selection through, and the systematic guard is task 12.1's
job. It is worth fixing before then so the name does not license a false
assumption in between.

## Evidence

At `001aa91` with task 9.3's work applied:

- `tests/metrics/test_sources.py:1364` — the test name.
- Its body compares `sources.BANISTER_MALE_COEFFICIENT.value` against
  `stress._TRIMP_COEFFICIENT` and `sources.BANISTER_MALE_EXPONENT.value`
  against `stress._TRIMP_EXPONENT`. The two `BANISTER_FEMALE_*` bindings do
  not appear in it.
- `src/fitdocs/metrics/stress.py:55,58` — the only two weighting constants the
  module defines. `grep -n '0\.86\|1\.67' src/fitdocs/metrics/stress.py`
  returns nothing.

**Update 2026-07-29 — this item is now ACTIONABLE, and half its evidence above
is superseded.** fit-ingest task 11 landed at `0ae83aa` on `impl/fit-ingest`
(NOT merged to main), which is the unblocking event step 2 below names.

- **The core defect stands unchanged.** At `0ae83aa` the test still checks two
  of four terms. Confirmed by execution during task 11's verify pass: a
  mutation moving `BANISTER_MALE_COEFFICIENT.value` from 0.64 to 0.70 reds it,
  while a mutation making `stress.trimp` ignore its argument in favour of the
  male pair leaves it **green**.
- **Two stale citations above, both caused by task 11.** `stress.py:55,58` and
  the names `_TRIMP_COEFFICIENT` / `_TRIMP_EXPONENT` no longer exist anywhere
  in the tree — task 11 deleted both module constants when `trimp()` took the
  weighting pair as an argument. `git grep _TRIMP_COEFFICIENT` now returns only
  past-tense prose. Re-read the test against the current tree, not those lines.
- **The test moved and was rewritten.** It is now at
  `tests/metrics/test_sources.py:1374`, and its body asserts through
  `stress.trimp()`'s new signature rather than against module constants. Its
  docstring now states its own blind spot explicitly, so extending it must not
  contradict that sentence.
- **Prefer extending, not renaming.** Step 2 below made this conditional on
  task 11; the condition is met. `sources.weighting_for()` resolves either
  curve, so all four terms are now reachable from one resolver call.

Reported by the task-9.3 verification reviewer as a secondary observation; the
`file:line` readings above were confirmed in this session.

## How to pick it up

1. Decide which way to close it. Renaming is the honest one-line fix:
   `test_the_male_weighting_terms_bound_values_match_stress_py`, with a
   docstring sentence saying the female pair has no module constant to check
   against until task 11 threads the selection through.
2. Extending it is only possible once `stress.py` reads its weighting from
   `WEIGHTING_PAIRS` (task 11). If this item is picked up after task 11 lands,
   prefer extending: assert all four against whatever the resolver returns.
3. Either way, add the mutation: change the value the test compares against and
   confirm it reds, so the renamed or extended test is pinned rather than
   assumed. Run it through `uv run pytest`, never `uv run python -c`.

Done means: the test's name describes exactly what its body checks, and a
mutation proves the body can fail.
