---
id: 2026-09-12-decline-kind-for-an-uncovered-sport
title: Uncovered-sport decline has no honest BenchmarkKind to name
status: open
importance: medium
importance_why: DerivationDeclined.kind is required, so an uncovered-sport decline (e.g. a swim page) must name a quantity it never attempted, contradicting Req 7.3's own wording.
effort: S
kind: gap
area: performance-benchmarks, src/fitdocs/performance/types.py, derive.py, cli.py
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "do: decide DerivationDeclined.kind's shape for the uncovered-sport case and update types.py/derive.py/cli.py"
context:
  - src/fitdocs/performance/types.py
  - src/fitdocs/performance/derive.py
  - src/fitdocs/cli.py
blocked_by: []
---

## What

`DerivationDeclined.kind` is required, so the uncovered-sport decline names
`LTHR_BPM` for a swim page — but Req 7.3's "the quantity it would have
produced" has no honest value for a sport the pass never attempted to
derive a quantity for. Separately, `lactate_threshold_hr` has no kind gate
at all: a fourth `EffortKind` member added to the router's `case` would
derive LTHR from it with no code naming that decision.

## Why it matters

The current decline for an uncovered sport is a fabricated answer to "what
quantity would this have produced" — it names a kind that was never
attempted. This is the same species of defect as reporting a fabricated `0`
for absent data, which tech.md forbids.

## Evidence

- (3.4 reviewer) "DerivationDeclined.kind is required, so an uncovered-sport
  decline must name a quantity never attempted (LTHR_BPM chosen); Req 7.3
  'the quantity it would have produced' has no honest value. Consider
  `kind: BenchmarkKind | None` or a report-rendering convention in 4.4."
- (3.4 r2 reviewer) "lactate_threshold_hr has no kind gate, so a fourth
  EffortKind member appended to _covered_effort_kind's case would derive
  LTHR from it with no code naming that decision."

## How to pick it up

1. Read `DerivationDeclined` in `types.py`, the uncovered-sport decline
   path in `derive.py`, and how 4.4's report rendering (`cli.py`) consumes
   `kind`.
2. Decide between `kind: BenchmarkKind | None` and a rendering convention
   for "no kind attempted"; implement whichever is chosen.
3. Add an explicit gate/comment in `_covered_effort_kind`'s `case` (or
   equivalent) naming the decision that a new `EffortKind` member does not
   automatically derive LTHR.

## Open questions

- `kind: BenchmarkKind | None` vs a rendering-only convention — the design
  does not currently decide this.
</content>
