---
id: 2026-09-12-athlete-benchmarks-design-not-amended-for-source
title: athlete-benchmarks design.md not amended in place for the source field
status: open
importance: medium
importance_why: Amendment 2 only touched the Non-Goals line; the design's Benchmark sketch, signature, traceability table, and data model still describe a Benchmark with no source, so the design misrepresents the shipped shape.
effort: S
kind: docs
area: athlete-benchmarks, .kiro/specs/athlete-benchmarks/design.md, spec.json
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "/kiro-spec-design athlete-benchmarks [queue: .kiro/queue/2026-09-12-athlete-benchmarks-design-not-amended-for-source.md] amend design.md in place for the source field"
context:
  - .kiro/specs/athlete-benchmarks/design.md
  - .kiro/specs/athlete-benchmarks/spec.json
  - src/fitdocs/benchmarks.py
blocked_by: []
---

## What

Amendment 2 changed only the Non-Goals line in `design.md`. The following
sections still do not know about `source`:

- The `Benchmark` sketch (~lines 566-572)
- The `with_benchmark` signature (~line 889)
- The traceability table (~lines 462-500)
- The physical data model (~line 1211+)
- The Domain Model line (~line 1201)

Additionally, Amendment 2 has no criterion for a non-table `source` value,
which `benchmarks.py` rejects — the design is silent on that validation
boundary.

Separately, `spec.json`'s `amendments[1].cross_spec` assigns
`_merge_benchmarks_document` to training-load, while the design's §
BenchmarkStore claims ownership of it.

## Why it matters

A reader of the design's `Benchmark` sketch, signature, or data model
sections gets a shape that does not match the shipped `source`-aware
`Benchmark`. The `spec.json` cross_spec ownership conflict points two
sessions at different owners for the same function.

## Evidence

- (5.3 reviewer) "athlete-benchmarks design.md not amended in place for
  `source`: Benchmark sketch (~566-572), with_benchmark signature (~889),
  traceability table (~462-500), physical data model (~1211+), Domain Model
  line (~1201). Task 5.3 only requires the Non-Goals line."
- (5.3 r2 reviewer) "Amendment 2 has no criterion for a non-table `source`
  value (benchmarks.py rejects it). Fold into the design-in-place
  follow-up."
- (5.3 r2 reviewer) "spec.json amendments[1].cross_spec assigns
  _merge_benchmarks_document to training-load while athlete-benchmarks
  design § BenchmarkStore claims it. wording only."

## How to pick it up

1. Read Amendment 2 in `design.md` and diff its scope against the sections
   listed above.
2. Amend each listed section in place to reflect `source`, including a
   stated criterion for what counts as a valid non-table `source` value per
   `benchmarks.py`'s rejection behavior.
3. Reconcile `spec.json`'s `amendments[1].cross_spec` ownership of
   `_merge_benchmarks_document` with § BenchmarkStore's claim.
</content>
