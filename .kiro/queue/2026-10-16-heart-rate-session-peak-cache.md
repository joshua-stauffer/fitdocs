---
id: 2026-10-16-heart-rate-session-peak-cache
title: Design a per-session sustained-HR peak cache with explicit ownership and invalidation
status: open
importance: medium
importance_why: Every derivation re-parses eligible archives; prior corpus measurements identify repeated parse and compose work.
effort: L
kind: spec-work
area: hr-derivation, src/fitdocs/hr_benchmarks/engine.py
created: 2026-10-16
surfaced_by: /kiro-impl hr-derivation task 5.2
pinned_at: dcdbdd1
resume_command: "/kiro-discovery [queue: .kiro/queue/2026-10-16-heart-rate-session-peak-cache.md] Design an explicitly owned and invalidated per-session sustained-HR peak cache preserving benchmark outputs and failure reports"
context:
  - .kiro/specs/hr-derivation/requirements.md
  - .kiro/specs/hr-derivation/design.md
  - .kiro/specs/hr-derivation/research.md
  - .kiro/specs/hr-derivation/tasks.md
  - src/fitdocs/hr_benchmarks/engine.py
  - src/fitdocs/hr_benchmarks/peaks.py
  - src/fitdocs/hr_benchmarks/types.py
  - src/fitdocs/hr_benchmarks/sources.py
  - src/fitdocs/compose/archive.py
  - src/fitdocs/docio.py
  - src/fitdocs/layout.py
  - tests/hr_benchmarks/test_engine.py
  - tests/hr_benchmarks/test_peaks.py
  - tests/hr_benchmarks/test_determinism.py
  - .kiro/steering/change-protocol.md
  - .kiro/queue/README.md
blocked_by: []
---

## What

Design a cache of per-session sustained-HR peaks so repeated `derive-benchmarks`
runs can avoid unchanged archive parsing and composition. The current HR design
explicitly defers this cache and permits only the athlete-profile mutation.
A follow-up must establish its I/O owner, storage contract and invalidation
rules before implementation; keep the pure peak calculation free of I/O.

## Why it matters

Unchanged derivations repeat archive reads, FIT parsing and listed composition.
Prior discovery measured this component at 216 seconds for 2,564 documents,
about 84 milliseconds per document. This implementation run did not reproduce
that maintainer-corpus measurement, and no current wall-clock runtime or cache
speedup is claimed.

## Evidence

- At `dcdbdd1`, `src/fitdocs/hr_benchmarks/engine.py:150-152`
  composes each eligible page from `source_refs(frontmatter)` and
  `parse_fit(archive.read_bytes())` during the evidence walk. Source inspection
  confirms this repeated work; it is not a new performance measurement.
- `.kiro/specs/hr-derivation/research.md:25-33` and `:159-164` record the
  prior 2026-10-12 discovery measurement: parse/compose 216 seconds for
  2,564 documents. Its old 305-second total included a quadratic scratchpad
  peak search and must not be presented as the current implementation runtime.
- `.kiro/specs/hr-derivation/design.md:44` excludes a peak cache, and
  `:1271-1275` / decision 11 defer it. Task 5.2 explicitly requires this
  follow-up. Optional real-data task 5.3 remains unrun.
- Filing-time dedup read all 460 open queue frontmatters and 461 root
  Markdown bodies, plus searched the current roadmap. Only the separate
  cadence-span full-rescans item mentions the cache; no duplicate or open
  roadmap item owns it.

## How to pick it up

1. Read the HR design's boundaries, engine evidence walk and research attribution.
   Confirm the current parse/compose call path and measure a representative
   workload if approved data is available; retain absence as unknown.
2. Use discovery to define ownership and invalidation before changing code.
   Account for ordered listed references and their content, selected base and
   resolver behavior, filters, cadence policy, and algorithm/source versions.
   Preserve workout page/date associations, raw fractional peak values,
   no-evidence reasons, skip/failure reports and terminal progress. Decide
   explicitly how current missing or unreadable archives invalidate cached
   success and preserve the existing failure-retention behavior.
3. Implement only after the new boundary/storage contract is approved. Verify
   cold/warm/invalidation behavior and byte-identical benchmark results,
   unchanged-run semantics and reports against the uncached calculation.
   Cover changes in archives, composed refs, flags and failure states, and
   demonstrate performance using new attributed measurements.

## Open questions

Which component owns the cache and its location, lifecycle and schema? What
invalidation identity preserves current read failures while avoiding repeated
parsing? These are follow-up design decisions, not permission to add cache I/O
to the current pure peak module or athlete-only writer.
