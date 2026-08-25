---
id: 2026-08-25-insufficiency-provenance-fixtures-sit-at-the-identity-point
title: The insufficiency provenance fixtures run at exactly 100% coverage, tying covered_s, total_s and scored_duration_s into one indistinguishable value
status: open
importance: low
importance_why: Two realistic field-source swaps are invisible to the module that exists to pin them; both are caught elsewhere today, so nothing is unguarded repo-wide.
effort: S
kind: gap
area: load-channels, tests/load/channels/test_insufficiency.py
created: 2026-08-25
surfaced_by: /kiro-impl load-channels (task 5.2 review, reviewer mutations R8/R9; R8 reproduced by the parent session)
pinned_at: c6c1bb1
resume_command: "do: change one of the three provenance fixtures in tests/load/channels/test_insufficiency.py from full coverage to a comfortable margin (e.g. 180 covered of 200, fraction 0.90) so covered_s, total_s and scored_duration_s stop being tied, then verify a covered/total swap and a scored_duration_s source swap both red inside that module"
context:
  - tests/load/channels/test_insufficiency.py
  - src/fitdocs/load/channels/power.py
  - src/fitdocs/load/channels/sufficiency.py
  - .kiro/specs/load-channels/tasks.md
blocked_by: []
---

## What

The three provenance tests in `tests/load/channels/test_insufficiency.py`
(`:523`, `:541`, `:561`) build a fully-covered stream with `n = 200`. At 100%
coverage:

```
coverage.covered_s == coverage.total_s == scored_duration_s == 200.0
coverage.fraction  == 1.0
```

Four quantities collapse to two values, so assertions cannot tell them apart.
This is the repo's named **identity point** trap — the same shape as task 3.3's
`threshold_speed_mps`, which was freely swappable because its fixture sat
exactly at threshold.

Task 5.2's own bullet asks that a computed result carry its coverage and
duration *"even when the gate passed **comfortably**"*. `1.0` is not a
comfortable margin; it is the boundary value where the distinctions vanish.

## Why it matters

Measured consequence — two realistic one-line production swaps are invisible to
the module whose job is to pin these fields:

- sourcing `scored_duration_s` from `coverage.total_s` instead of `moving_time_s`
- swapping `covered_s` / `total_s` in the constructed `StreamCoverage`

Neither leaves the repository unguarded — the first is caught by
`test_power.py::test_intensity_relation_holds_at_a_sub_threshold_effort`, the
second by `test_sufficiency.py` — which is why this is `low` and was not a
rejection ground. The concern is that the module a future session will read as
*the* provenance pin does not actually discriminate these fields, so a change
that also touched the catching tests would sail through.

## Evidence

Reproduced by the parent session at `c6c1bb1`. Mutation: `power.py`'s
`scored_duration_s=moving_time_s` → `scored_duration_s=coverage.total_s`.

```
$ uv run pytest -q tests/load/channels/test_insufficiency.py
21 passed in 0.05s

$ uv run pytest -q
FAILED tests/load/channels/test_power.py::test_intensity_relation_holds_at_a_sub_threshold_effort
1 failed, 2704 passed, 5 skipped
```

Reverted; `git diff --stat HEAD -- src/` empty afterwards.

The covered/total swap (reviewer mutation R9, caught by `test_sufficiency.py`
with 23 red) was **reported by the task 5.2 reviewer and not independently
reproduced here**.

Fixture sites: `tests/load/channels/test_insufficiency.py:523`, `:541`, `:561`,
each opening `n = 200` with a fully-covered stream.

## How to pick it up

1. Open `tests/load/channels/test_insufficiency.py:523` and read the three
   provenance tests together — they share the fixture shape.
2. Change at least one to a comfortable margin: 180 covered of 200 gives
   `fraction 0.90`, safely above the 0.80 default minimum, and leaves
   `covered_s` (180), `total_s` (200) and `scored_duration_s` pairwise distinct.
3. Verify both swaps above now red **inside this module**, not only elsewhere.
   Run them through `uv run pytest` — a bare interpreter reads stale bytecode.
4. Keep the assertions' expected values distinct per channel; do not introduce a
   tie in the process of removing one.

**Done** looks like: a covered/total swap and a `scored_duration_s` source swap
each red a named test in `test_insufficiency.py`.

## Open questions

None. The fixture change is mechanical and the two verifying mutations are
named above.
