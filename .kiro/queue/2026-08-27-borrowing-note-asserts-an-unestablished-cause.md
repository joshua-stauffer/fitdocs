---
id: 2026-08-27-borrowing-note-asserts-an-unestablished-cause
title: The borrowing note says "no X threshold is on file" for a threshold that IS on file, just future-dated
status: open
importance: high
importance_why: A false factual sentence lands in the athlete's workout document, and the two materially different profiles produce byte-identical output.
effort: S
kind: correctness
area: threshold-load, src/fitdocs/load/threshold/anchors.py, src/fitdocs/load/threshold/calculator.py
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
pinned_at: 3e14ab9
resume_command: "/kiro-impl threshold-load [queue: .kiro/queue/2026-08-27-borrowing-note-asserts-an-unestablished-cause.md] Record why a Borrowing borrowed, and render the honest note"
context:
  - src/fitdocs/load/threshold/anchors.py
  - src/fitdocs/load/threshold/calculator.py
  - tests/load/threshold/test_anchoring_e2e.py
blocked_by: []
---

## What

`anchors.py:114-140` borrows from a later chain entry for **two** distinct
reasons: `has_benchmark` is false (line 122 — not on file at all), or
`has_benchmark` is true but `profile.benchmark(..., on=on)` returns `None`
(lines 125-126 — on file but dated after the activity). `Borrowing`
(`anchors.py:60-71`) records `kind`/`activity_discipline`/`anchor_discipline`
and **not which reason**.

`calculator.py:531-541` then renders one note as if only the first existed:

```
f"{channel_label} channel anchored on the {borrowing.anchor_discipline} "
f"{quantity_name}; no {borrowing.activity_discipline} threshold is on file."
```

This is the same shape as two other findings on this spec: **a string built
from one input while the condition that produced it tested two.**

## Why it matters

Measured — two profiles differing only in whether a Walk LTHR exists produce
**byte-identical** notes:

| profile | note |
|---|---|
| Walk LTHR absent, Run LTHR applicable | `Heart-rate channel anchored on the Run lactate threshold heart rate; no Walk threshold is on file.` |
| Walk LTHR on file dated 2030-01-01 (activity 2026-06-01) | *identical* |

In the second the sentence is simply false. It lands in a generated document.
Reachable in normal use: an athlete who tests a walking LTHR today and
re-runs `fitdocs load` over past walks gets it on every one of them.

## Evidence

`3e14ab9`. Every borrowing fixture uses the honest case —
`tests/load/threshold/test_anchoring_e2e.py:404` dates `_WALK_LTHR`
2026-02-01, before the 2026-06-01 activity; `test_result_assembly.py:456-478`
constructs a `Borrowing` directly. Per-task review of 2.3 sees a correctly
recorded `Borrowing`; per-task review of 3.2 sees a note matching
`design.md:1178-1180` exactly. Only the seam shows the falsehood.

## How to pick it up

Add the reason to `Borrowing` (e.g. `reason: Literal["not_on_file",
"not_applicable"]`), then branch the note in `_format_borrowing`. Pin it with
two fixtures differing **only** in the borrowed-from discipline's benchmark
date, asserting the notes differ. Related: this is the same `not_applicable`
information the calculator currently never reads — see
`2026-08-27-not-applicable-has-no-readers`.
