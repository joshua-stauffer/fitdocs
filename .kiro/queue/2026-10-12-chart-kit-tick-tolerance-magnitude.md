---
id: 2026-10-12-chart-kit-tick-tolerance-magnitude
title: ticks: float tolerance scales with input magnitude
status: open
importance: medium
importance_why: Direct clock arithmetic still uses magnitude-scaled tolerance; linear precision is repaired below.
effort: S
kind: defect
area: chart-kit kit/ticks.py
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-tick-tolerance-magnitude.md] ticks: float tolerance scales with input magnitude"
context:
  - src/fitdocs/render/charts/kit/ticks.py
  - src/fitdocs/render/charts/kit/scales.py
  - tests/render/charts/kit/test_linear_precision.py
  - tests/render/charts/kit/test_cells.py
blocked_by: []
---

## What
`_TOLERANCE * max(|lo|,|hi|) / step` grows with magnitude: ~64 s for epoch seconds in clock_ticks (scales now works around it by passing seconds relative to midnight), and for linear_ticks on large numbers the rounding can leave nice=True ticks that do not enclose the data.

## Why it matters
Any caller passing large absolute values (epoch seconds, big counters) gets ceil/floor behaving like round.

## Evidence
4.1 review: clock_ticks on epoch seconds misplaced ticks; clock_ticks(43220.0, 43800.0, 8) correct. ticks.py:166,:357 (at d03e85e).

- chart-catalog (2026-10-12, c52da2d): the non-enclosure also happens for SMALL values: `linear_ticks(0, 0.1 + 0.2, 6)` ends at 0.3 < hi (rounding to 12 significant figures + `_ceil` snapping within tolerance), while the `linear_ticks` docstring (`ticks.py` ~line 148) says the outermost ticks enclose the data. `cells.BinnedScale.classify` now clamps a value above the last edge into the top bin as a workaround (design § Cells amended, task 1.4). Fixing the tick contract would let that clamp go.

## How to pick it up
The linear portion is repaired (see the 2026-10-17 evidence below). Start with
the remaining direct clock arithmetic in ticks.py and its relative-midnight
consumer in scales.py. Reproduce epoch-second behavior before changing it;
preserve the repaired linear regressions. Remove the relative-base and cells
above-edge clamp workarounds only with independent contract/regression evidence.
The current repair intentionally retains both workarounds.

Original pickup instruction, retained as history: make tolerance relative to the
step or span instead of magnitude, add large-linear and epoch-clock tests, and
consider removing the relative-base workaround after repairing ticks.


## Linear portion repaired during Recovery implementation (2026-10-17)

Valid constant SDNN73 yielded an unrounded geometric mean72.99999999999999.
The former magnitude-scaled quotient slack and twelve-significant-digit
construction collapsed linear ticks, causing reference-band/line math-domain
errors and small-multiples IndexError. The separately scoped chart-kit repair
constructs decimal ladder multiples once, corrects represented outer boundaries
and accepts only finite, distinct, increasing, enclosing candidates of valid
cardinality. No Recovery method or mean is rounded.

New regressions retain adjacent/signed/large/small enclosure cases, exact
nice=False extents including an unaligned tiny span, public chart rendering,
and a real constant-data inbox-to-Recovery case. Two old cells cases now assert
enclosure rather than the former defect; their classification assertions and
the separate explicit above-edge clamp test remain intact. Existing ordinary
decimal, integer, duration and other scale-family tests remain.

Fresh independent review and parent FIX verification: full original24391passed,
44expectedskips, exit0; assigned5714passed; Ruff798/mypy613/diff clean. Thirty-three
distinct claimed production states plus two independent faults gave145native
assertion RED/restoredGREEN observations and cover18new/changed sites89roles.
The preserved original constant fixture also renders the page and all six
populated SVGs. Evidence outside the working tree:
 /private/tmp/recovery-scale-precision-verification.json and
 /private/tmp/recovery-scale-precision-review-remediation1.md.

This item remains open for direct clock arithmetic and deliberate evaluation
of the two retained workarounds. This repair made no new clock execution claim:
the original clock evidence above is historical, and clock/global floor/ceil,
relative-midnight scaling and cells.py are unchanged.
