---
id: 2026-09-10-performance-benchmarks-design-predates-applies-from
title: performance-benchmarks' benchmark-entry shape predates wave 0's applies_from field — amend before implementing tasks 2.1–2.3 and 5.3
status: done
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

## Update 2026-09-10 (wave 0 landed: training-load Amendment 4 merged to main)

The shape wave 0 leaves, so the amendment can be written against code rather
than the log line:

- `fitdocs.benchmarks.Benchmark` fields, in order: `kind, discipline, value,
  measured_on, note, applies_from`; `applies_from: date | None = None` is
  trailing and defaulted. `source` goes after it.
- `benchmarks_to_document` emits `value`, `measured_on`, then `applies_from`
  only when present; the group sort key is `measured_on` alone and is pinned
  against `applies_from` by
  `tests/test_benchmarks.py::test_serializer_sorts_mixed_group_by_measured_on_not_applies_from`.
  A `source` sub-table must not change the sort key either — add the same
  mixed-group fixture for it. Omitting a `None` field is load-bearing for the
  store's merge (see the function's docstring).
- `AthleteProfile.with_benchmark(kind, *, discipline, value, measured_on,
  note=None, applies_from=None)`; a `source=` keyword goes last.
- `_merge_benchmarks_document` in `src/fitdocs/load/profile.py` overlays
  whatever keys the fresh serialized record carries and leaves existing keys
  the record omits untouched — that is how `note` and `applies_from` are
  both preserved on a rewrite that does not mention them. It has **no scope
  conditional**; the 7.2 reviewer noted that an athlete-scope-only
  regression in preserve/overlay would pass the store suite because no
  fixture varies scope through the merge. When the two-half overlay rule for
  `source` lands, keep the merge scope-agnostic and add athlete-wide fixtures
  for every overlay branch.
- `BenchmarkSet.applicable` is two-tier: a derived entry with no
  `applies_from` is tier-1 only, exactly like a hand-written one; derived
  entries need no `applies_from` (roadmap Phase 6).
- Lesson from seven review rounds on 7.1 (tasks.md § Implementation Notes
  "From task 7.1"): enumerate layers × scopes × kinds × group shapes before
  the first report on any task that adds a field to this entry shape.

## Resolution

**Closed 2026-09-10** — resolved by performance-benchmarks Amendment 1, merged
to `main` at `7541553` (`spec/perfbench-applies-from`, ff-only, worktree and
branch removed).

Written against wave 0's landed code, not against the peer's log line, as this
item's own step 1 required. Verified at close:

- `Benchmark` field order read out of `src/fitdocs/benchmarks.py`:
  `kind, discipline, value, measured_on, note, applies_from`. Emitted key order
  read out of `benchmarks_to_document`: `value, measured_on, applies_from,
  note`. **The two differ**, which the amendment now states explicitly — the
  original design's "emits `source` after `note`" was accidentally still true
  for the wrong reason.
- `design.md:1039-1040` — `source` is the fifth field, appended after
  `applies_from`.
- `design.md:1063-1075` — `source` emitted last; group sort key stays
  `measured_on` alone, with the `source` mixed-group fixture required and
  `::test_serializer_sorts_mixed_group_by_measured_on_not_applies_from` named
  as the one it belongs beside. Same requirement on `tasks.md:231-236`.
- `design.md` cross-spec obligations 1–7 — the deriver never writes
  `applies_from` (so a derived entry is tier-1 only), the merge stays
  scope-agnostic with an athlete-wide fixture owed on every overlay branch, and
  the 7.1 "enumerate layers × scopes × kinds × group shapes" lesson is carried
  into both documents.
- `tasks.md` — task 5.3 lands as `athlete-benchmarks` **Amendment 2** and is
  told to read that spec's post-Amendment-1 text rather than the pre-merge line
  numbers. Tasks were amended in place: `git diff 4b76906..7541553` shows no
  task line added, removed or renumbered (23 leaf tasks before and after), so
  step 3's "regenerate only if wording changes" was satisfied without a
  regeneration.
- `spec.json` — phase `tasks-generated`, all approvals true,
  `ready_for_implementation` true, unchanged; one `amendments` entry recording
  the correction and the ruling below.

**The open question this item raised is answered, and one it did not raise was
found.** "Whether a derived entry may ever carry `applies_from`" → never by the
deriver, freely by hand; a hand-added one survives a refresh under the
inherit-on-absent rule. Beyond that, the independent review gate (round 1
NEEDS_FIXES: 1 blocking, 2 should-fix, 5 notes, all applied) found that the
first draft asserted away a real interaction: a derived entry measured *inside*
an athlete's declared `applies_from` window has no same-date collision, so the
pass writes it, and it then wins tier 1 for activities in the overlap. **Ruled
accepted** — `athlete-benchmarks` Req 3.10 makes tier 1 beat tier 2
unconditionally, and Requirement 6's "shadow" is date-scoped throughout — so
the pass does not decline on window overlap, and the shadowing invariant plus
the 6.1/6.2 traceability line are qualified to "on its own date". Declining
instead would be a behavioural change needing its own criterion.

Filed rather than folded in: `2026-09-10-resolve-archive-citation-stale` (a
pre-existing wrong line range for `_resolve_archive`, correct before wave 0 too,
so out of this amendment's scope).
