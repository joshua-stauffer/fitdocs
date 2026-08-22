---
id: 2026-07-27-traceability-table-supports-references-not-repinned
title: design.md's Requirements Traceability table (and one Arbitration-component
  paragraph) still name bare `supports`, not `supports_activity`
status: open
importance: low
importance_why: Purely documentation drift with no behavior at stake — the
  ruling and the shipped code (`load/types.py:380`) both already use
  `supports_activity`, so nothing computes wrong. Cost is to a reader who
  greps the traceability table (the spec's canonical Requirement-to-mechanism
  index) and finds a symbol that no longer names a real member on
  `LoadCalculator`.
effort: S
kind: inconsistency
area: training-load, .kiro/specs/training-load/design.md
created: 2026-07-27
surfaced_by: review of chore/training-load-spec-repin (queue item
  2026-07-26-training-load-own-supports-references-not-repinned, whose
  "three sites" scope this item falls outside of)
pinned_at: 54a9799
resume_command: "do: repin the four remaining bare `supports` references in
  .kiro/specs/training-load/design.md to `supports_activity` (or to
  `supports_activity(calculator, activity)` where a full call is named),
  matching the mechanism already used at the repinned revalidation trigger,
  the Req 1.14 traceability row, and load/types.py:380's docstring [queue:
  .kiro/queue/2026-07-27-traceability-table-supports-references-not-repinned.md]"
context:
  - .kiro/specs/training-load/design.md
  - src/fitdocs/load/types.py
blocked_by: []
---

## What

`design.md`'s Requirements Traceability table has three rows whose
`Interfaces` column still names the bare, withdrawn `LoadCalculator.supports`
Protocol member instead of the module-level `supports_activity(calculator,
activity)` that replaced it (ruling recorded at `design.md:815`, shipped in
`src/fitdocs/load/types.py`):

- Req 1.6 row: `` `for_modality` narrowed by `supports` ``
- Req 3.1 row: `` `supports` → `collect_missing_fields` ``
- Req 10.2 row: `` `supports`-narrowed candidates, `Ambiguous` ``

A fourth site, inside the Arbitration component's LoadEngine prose (not the
table), has the same problem: "so its no-default branch can narrow candidates
by `supports`".

## Why it matters

Per `src/fitdocs/load/types.py:380`'s own docstring, both arbitration and the
engine's support gate call `supports_activity`, never `calculator.supports`
directly — that member does not exist on the `LoadCalculator` Protocol and
was deliberately rejected as unimplementable (`design.md:815`'s ruling). A
reader who trusts the traceability table's `Interfaces` column — the sole
per-requirement index into "what implements this" — over the prose above it
will look for a `.supports` attribute that is not there.

This is the same defect the now-closed(-in-branch, proposed) queue item
`2026-07-26-training-load-own-supports-references-not-repinned` fixed at
three *other* sites (the revalidation trigger, the Req 1.14 row, and
`tasks.md`'s Amendment 3 summary) — these four are additional instances that
fell outside that item's three named sites and were not caught by the same
pass.

## Evidence

Verified at `54a9799`:

- `.kiro/specs/training-load/design.md:679` — Req 1.6 row, `` `for_modality`
  narrowed by `supports` ``.
- `.kiro/specs/training-load/design.md:696` — Req 3.1 row, `` `supports` →
  `collect_missing_fields` ``.
- `.kiro/specs/training-load/design.md:723` — Req 10.2 row, ``
  `supports`-narrowed candidates, `Ambiguous` ``.
- `.kiro/specs/training-load/design.md:1552` — Arbitration component prose,
  "narrow candidates by `supports`".
- `src/fitdocs/load/types.py:380` — `supports_activity`'s docstring, the
  mechanism both arbitration and the engine gate actually call.
- `.kiro/specs/training-load/design.md:815` — the ruling that rejected the
  `LoadCalculator.supports` Protocol-member form as unimplementable in
  Python.

Not affected, and not part of this item — `design.md:327`, in the
cross-spec coordination table, describes `threshold-load` *defining its own*
`supports(activity)` method; a calculator defining its own narrowing still
defines a method literally named `supports`, which is correct as written
per the ruling at `design.md:815`.

## How to pick it up

1. Read `design.md:815`'s ruling paragraph and `load/types.py`'s
   `supports_activity` docstring to confirm the mechanism before editing.
2. Repin the four sites listed under Evidence to `supports_activity`,
   preserving each row/paragraph's surrounding meaning (e.g. "narrowed by
   `supports_activity`" not just a bare rename that breaks the sentence).
3. Grep `design.md` once more for `` `supports` `` (backtick-bounded, to
   exclude `supported_modalities` and `supports_activity` itself) to confirm
   no other stray site remains, and separately confirm `design.md:327`
   (threshold-load's own method) is left untouched.
4. Done means: every reference to the arbitration/engine support mechanism in
   `design.md` reads `supports_activity`, and a `grep -n '\`supports\`'
   design.md` returns nothing outside the threshold-load
   own-`supports`-method site.

## Open questions

None — this is a mechanical repin of the same kind already completed at
three sibling sites, with the same source of truth.
