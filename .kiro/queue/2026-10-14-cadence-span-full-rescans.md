---
id: 2026-10-14-cadence-span-full-rescans
title: Scan paired cadence samples once instead of rescanning them for every span
status: open
importance: medium
importance_why: Long recordings make cadence measurement quadratic in sample count, and the heart-rate peak stage invokes that measurement twice for runs.
effort: S
kind: chore
area: activity-qa-flags, src/fitdocs/load/qa/cadence.py
created: 2026-10-14
surfaced_by: /kiro-impl hr-derivation task 2.3 independent review
pinned_at: 0343188
resume_command: "do: make cadence.span_statistics partition paired samples in one ordered pass while preserving raw span boundaries and statistics; verify output equivalence and deterministic operation-count scaling"
context:
  - src/fitdocs/load/qa/cadence.py
  - src/fitdocs/model.py
  - tests/load/qa/test_cadence_spans.py
  - tests/load/qa/test_cadence.py
  - .kiro/specs/activity-qa-flags/requirements.md
  - .kiro/specs/activity-qa-flags/design.md
  - .kiro/specs/hr-derivation/design.md
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`span_statistics` loops over full-width spans at
`src/fitdocs/load/qa/cadence.py:193-199` and searches every paired sample
again for each span. Its time-index reads are `2 + n * span_count` on a
fully paired recording. The new heart-rate peak search is linear, but its
required calls to `cadence.detect` and then `cadence.span_statistics` for
running recordings retain this upstream cost.

## Why it matters

With a fixed sample interval and span width, both sample count and span count
grow with recording duration, making this selection work quadratic. This
affects the existing QA pass as well as heart-rate derivation. It is an
optimization of the activity-qa-flags boundary, separate from the planned
per-session peak cache. No output defect or wall-clock speedup is claimed.

## Evidence

The source at `0343188` is unchanged from main's cadence implementation.
The reviewer used a tuple subclass that counts `Samples.time_s` indexing,
with invented non-decreasing times, paired HR/cadence values and a ten-second
window. The controller inspected and independently reran that probe with
the repository's pytest setup:

```text
UV_CACHE_DIR=/private/tmp/fitdocs-hr-uv-cache UV_OFFLINE=true uv run --no-sync pytest tests/hr_benchmarks/test_peaks.py /private/tmp/hr_task23_review_cadence_probe.py -q -s
n=101, spans=10, time-index reads=1012; expected=1012
n=201, spans=20, time-index reads=4022; expected=4022
48 passed in 0.10s
```

The probe constructs times `0..n-1`, HR `140 + t % 7`, and cadence `HR/2`.
After resetting the tuple's read counter it calls the real
`span_statistics(window_s=10, settings=FlagSettings())`. It asserts the
full span count, exact read count, and that every returned span is locked.
The operation counts can be reproduced without timing or production edits.
All 458 open queue frontmatters and the roadmap were checked; no existing
item owns these repeated sample scans.

## How to pick it up

1. Read the cadence measurement and verdict functions, the Samples time-order
   contract, and the existing span tests. Preserve anchoring at the first paired
   time, half-open full-width spans, discarded partial tails, raw points and
   current statistics; do not resample, interpolate or forward-fill.
2. Reproduce the two operation counts above, then partition the ordered paired
   indices with one advancing cursor or equivalent linear grouping. Compare
   every returned statistic against independent expected values and the old
   behavior on sparse and boundary fixtures.
3. Run `uv run pytest tests/load/qa tests/hr_benchmarks`, plus repository static
   checks. Done means outputs remain equivalent and a deterministic scaling
   check rejects the old per-span full-array scan without relying on timing.
