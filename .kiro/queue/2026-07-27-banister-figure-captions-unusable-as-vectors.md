---
id: 2026-07-27-banister-figure-captions-unusable-as-vectors
title: Banister 1991's worked examples do not satisfy Banister's own equation — do not use them as test vectors
status: open
importance: medium
importance_why: load-channels design.md requires a worked Banister TRIMP example for the heart-rate channel. The three examples printed in the primary text are the obvious thing to reach for and all three are wrong — one is not even internally consistent. A session that pins them will produce a confidently-cited test that contradicts the shipped formula.
effort: S
kind: trap
area: load-channels, tests, docs/reference/banister-trimp-primary-sources.md
created: 2026-07-27
surfaced_by: recomputing every worked example in the primary text (docs/reference/banister-trimp-primary-sources.md §5 D4)
pinned_at: c3d2201
resume_command: "do: when writing the heart-rate channel's worked TRIMP example, compute it from the formula rather than quoting Banister's figure captions — see the arithmetic in the queue item [queue: .kiro/queue/2026-07-27-banister-figure-captions-unusable-as-vectors.md]"
context:
  - docs/reference/banister-trimp-primary-sources.md
  - .kiro/specs/load-channels/design.md
  - src/fitdocs/metrics/stress.py
blocked_by: []
---

## What

Banister 1991 prints three worked TRIMP examples in its figure captions
(Figs. 9.5 and 9.6, pp. 409–410). All three assume HR_max = 200, HR_rest = 50.
None of them agrees with the equation printed one page earlier:

| Figure | T (min) | HR | x | stated y | stated TRIMP | y from the equation | TRIMP from the equation |
|---|---:|---:|---:|---:|---:|---:|---:|
| 9.5 | 10 | 150 | 0.667 | 2.5 | ~16.6 | 2.302 | 15.35 |
| 9.6 | 60 | 140 | 0.600 | 1.8 | 64.8 | 2.025 | 72.91 |
| 9.6 | 18 | 80 | 0.200 | 0.2 | 0.9 | 0.940 | 3.38 |

Rows 1 and 2 are at least internally consistent: `T × x × y` reproduces the
stated TRIMP from the stated `y`. The stated `y` simply is not what
`0.64·e^(1.92x)` gives — nor what the female curve gives, nor what Morton's
uncoefficiented form gives. Row 3 is not even internally consistent:
`18 × 0.2 × 0.2 = 0.72`, but the caption says 0.9 units (which would require
y = 0.25).

## Why it matters

`.kiro/specs/load-channels/design.md:377` requires "Worked example and
coefficient-invariance property" for the heart-rate channel, and design.md:1365
lists "the Banister TRIMP case" among the worked cases to pin. The natural move
for a session implementing that is to quote the primary text's own numbers —
which is normally the *most* defensible thing to do, and here produces a test
that disagrees with `stress.py` by 8–370% depending on the row. Worse, the
citation would be impeccable, so review by reading would pass it.

## Evidence

```
$ uv run python -c "
import math
for T,hr in ((10,150),(60,140),(18,80)):
    x=(hr-50)/150; y=0.64*math.exp(1.92*x)
    print(T,hr,round(x,4),round(y,4),round(T*x*y,3))"
10 150 0.6667 2.3018 15.346
60 140 0.6 2.0253 72.91
18 80 0.2 0.9396 3.383
```

against captions stating 16.6 (y=2.5), 64.8 (y=1.8) and 0.9 (y=0.2).

Full analysis: `docs/reference/banister-trimp-primary-sources.md` §5 D4.

## How to pick it up

1. Compute the worked example from the shipped formula and label it as computed,
   citing the primary text for the *formula* and not for the *numbers*.
2. If a source-quoted vector is wanted anyway, Morton 1990's RHM example
   (~125 trimps for 1 h at HR 150) is the better candidate — but its HR_max and
   HR_rest are unstated, so it pins the formula only up to those two unknowns.
   See §5 D1a.
3. Done looks like: a worked-example test whose expected value was produced by
   the formula under test's own definition, with a comment saying why the
   primary text's captions were not used.
