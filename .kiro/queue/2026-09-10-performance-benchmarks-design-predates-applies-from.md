---
id: 2026-09-10-performance-benchmarks-design-predates-applies-from
title: performance-benchmarks' benchmark-entry shape predates wave 0's applies_from field — amend before implementing tasks 2.1–2.3 and 5.3
status: open
importance: high
importance_why: Tasks 2.1–2.3 implement an entry shape (source as the fourth field, emitted after note, "emits three fields" today) that will be wrong the moment the in-flight wave 0 branch merges with applies_from as the fourth field; implementing from the spec as written would re-add or reorder a field a peer just landed.
effort: S
kind: inconsistency
area: performance-benchmarks, athlete-benchmarks, training-load, src/fitdocs/benchmarks.py, src/fitdocs/load/profile.py
created: 2026-09-10
surfaced_by: /kiro-spec-batch (Phase 6) — post-merge log read found the peer's TOUCHING line
pinned_at: bb848a4
resume_command: "/kiro-spec-design performance-benchmarks [queue: .kiro/queue/2026-09-10-performance-benchmarks-design-predates-applies-from.md] Amend the benchmark-entry shape for wave 0's applies_from: source is the fifth field, after applies_from"
context:
  - .kiro/specs/performance-benchmarks/design.md
  - .kiro/specs/performance-benchmarks/tasks.md
  - .kiro/specs/athlete-benchmarks/design.md
  - src/fitdocs/benchmarks.py
  - src/fitdocs/load/profile.py
blocked_by: []
---

## What
While the Phase 6 spec batch ran, the peer session `impl-training-load-prompt-date`
(wave 0, queue item `2026-08-27-prompt-date-strands-historical-documents`)
logged at 2026-09-09T22:15:37Z the shape it is landing: `Benchmark` gains a
trailing optional `applies_from: date | None = None` (≤ `measured_on`);
parser, serializer and `with_benchmark` carry it; `BenchmarkSet.applicable`
becomes two-tier; and it addressed performance-benchmarks directly: "add your
source field as a FIFTH entry field on top of this shape, do not re-add or
reorder." The batch controller did not re-read the log between its wave 1
claim and the wave 2 dispatch, so the performance-benchmarks spec was written
against the three-field entry on `main`.

## Why it matters
The spec's tasks 2.1–2.3 would implement `source` as the fourth field,
emitted after `note`, on a store whose fourth field is `applies_from`. The
two branches do not conflict textually today (wave 0 is uncommitted in its
worktree for `benchmarks.py`), so nothing will flag it — the implementer of
2.1 would simply build the wrong order and the peer's "do not reorder"
instruction would be violated by a session that never saw it.

## Evidence
- Shared agent log, `2026-09-09T22:15:37Z  impl-training-load-prompt-date  TOUCHING`
  — the shape statement quoted above; spec amendments already committed on
  `impl/training-load-prompt-date` at `1d86527` (training-load Amendment 4,
  athlete-benchmarks Amendment 1, threshold-load Amendment 2).
- `.kiro/specs/performance-benchmarks/design.md:223` — "`benchmarks_to_document`
  emits three fields" (four once wave 0 lands).
- `.kiro/specs/performance-benchmarks/design.md:950` — "**Serialization**
  (`benchmarks_to_document`): emits `source` after `note`" (must be after
  `applies_from`).
- `.kiro/specs/performance-benchmarks/tasks.md:18-24` — the entry shape the
  plan says it extends.
- `.kiro/specs/performance-benchmarks/tasks.md` task 5.3 amends
  `.kiro/specs/athlete-benchmarks/{requirements,design,spec.json}`, which the
  peer's Amendment 1 also rewrites (`git diff main...impl/training-load-prompt-date --stat`).

## How to pick it up
1. Wait for wave 0 to merge (or read its branch) and confirm the final
   `Benchmark` field order and the serializer's emitted key order.
2. Amend performance-benchmarks' design: `source` is the fifth field after
   `applies_from`; serializer emits it after `applies_from`; state that the
   deriver never sets `applies_from` on a derived entry (a derived entry is
   dated by `measured_on` = the effort's date; `applies_from` is
   athlete-declared) and that `is_recorded` / the never-overwrite rule are
   unaffected by it; re-point task 5.3 at athlete-benchmarks' post-Amendment-1
   text and line numbers.
3. Regenerate tasks in merge mode only if a task's wording changes; otherwise
   record the amendment in `spec.json` and the design, as the batch did.

## Open questions
Whether a derived entry may ever carry `applies_from` (e.g. the athlete later
declares that a derived FTP applied from an earlier date) — probably yes by
hand, never by the deriver; the amendment should say so.
