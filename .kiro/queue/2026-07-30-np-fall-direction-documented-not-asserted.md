---
id: 2026-07-30-np-fall-direction-documented-not-asserted
title: The falling NP direction is kept in a comment, not an assertion, in the frozen-literal form the sibling test explicitly rejects
status: open
importance: medium
importance_why: Three spec documents claim "both directions are pinned". Only the rise is. A future edit to the step fixture removes the falling case entirely with nothing failing, and the falling case is the one that falsifies the unconditional-direction claim this spec has now corrected five times.
effort: S
kind: gap
area: fit-ingest, tests/metrics/test_power.py
created: 2026-07-30
surfaced_by: adversarial review of spec/fit-ingest-np-window-criterion (queue-tier1 batch)
pinned_at: 9004329
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-np-fall-direction-documented-not-asserted.md] Assert the falling NP direction in test_normalized_power_exact_value_pins_fourth_power_exponent by recomputing the partial-window value live, matching _pre_amendment_partial_window_np"
context:
  - tests/metrics/test_power.py
  - tests/metrics/test_sources.py
  - src/fitdocs/metrics/power.py
blocked_by: []
---

## What

Task 13.1 made normalized power emit only complete rolling windows. The
direction that change moves NP is **conditional** on activity shape — it rises
when the dropped leading windows sit below the retained series, falls when the
activity opens at or above its own intensity.

Two fixtures exist, one per direction. Only the rising one asserts its
direction:

- **Rise** — `tests/metrics/test_power.py:304-305` asserts
  `np_value > old_partial_window_np`, and `tests/metrics/test_sources.py:2382-2418`
  recomputes the old value **live** via `_pre_amendment_partial_window_np`.
- **Fall** — `test_normalized_power_exact_value_pins_fourth_power_exponent`
  (`tests/metrics/test_power.py:181-238`) asserts only
  `approx(244.03877169307256)` and a loose `200.0 < np < 300.0` band. The
  partial-window value `261.09384206589294` appears **only in a comment at line
  214**, in no assertion.

So the fall is *documented*, not *pinned*.

## Why it matters

Three spec documents state that both directions are pinned by these two test
functions — `design.md:1716-1719`, `tasks.md:262`, `research.md:463-464`. That
claim is true of one and false of the other.

The falling case is the load-bearing one. It is the counter-example that
falsifies the unconditional "raises NP" claim which this spec has now had to
correct in five separate places. If a future session edits the step fixture,
the falling case disappears and nothing reds — leaving the spec asserting a
conditional direction whose only counter-example has silently evaporated.

The repo's own reasoning condemns the current shape. `tests/metrics/test_sources.py:2385-2396`
explains why the rising case is recomputed rather than frozen: a frozen literal
"is bound to the fixture that existed when it was written … so it can go stale
silently if the fixture below is ever changed." The falling case is left in
exactly the frozen-comment form that argument rejects.

## Evidence

Established by the reviewer on `spec/fit-ingest-np-window-criterion` at
`9004329`, by independent recomputation with exact `Fraction` arithmetic (the
module under test was never imported):

| fixture | complete-window | partial-window | Δ |
|---|---|---|---|
| 60 s @300 W → 60 s @100 W | 244.03877169307256 (n=91) | 261.0938420658929 (n=120) | **−17.06 W** |
| 29 s @0 W → 61 s @300 W | 265.66159423758893 (n=61) | 241.0463756814967 (n=90) | **+24.62 W** |
| constant 200 W × 2400 s | 200.0 (n=2371) | 200.0 (n=2400) | **0.00** |

The third row also shows the direction claim has a third case — no movement at
all — which no fixture asserts and which falsifies the "every activity with
power" universals still present at `design.md:184`, `:1573` and `:1826`.

## How to pick it up

1. Read `tests/metrics/test_sources.py:2382-2418` first — `_pre_amendment_partial_window_np`
   is the live-recomputation helper that already solves this problem for the
   rising case. Reuse it rather than writing a second mechanism.
2. Add the direction assertion to
   `test_normalized_power_exact_value_pins_fourth_power_exponent`, comparing
   against the recomputed partial-window value rather than the frozen
   `261.09384206589294` literal. The exact-value assertion already there should
   stay — it pins the fourth-power exponent, which is a different claim.
3. Consider whether the constant-power case (Δ = 0) deserves its own fixture,
   since it is currently the only one of three behaviours with no test and it
   is the one the surviving universals get wrong.
4. Done looks like: editing the step fixture's watt values breaks the falling
   direction assertion, and the three spec sentences claiming "both directions
   are pinned" become true.

## Open questions

None. The mechanism to copy already exists in the same test suite; this is
applying it one fixture over.
