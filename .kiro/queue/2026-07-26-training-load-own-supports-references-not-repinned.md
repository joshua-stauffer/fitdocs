---
id: 2026-07-26-training-load-own-supports-references-not-repinned
title: training-load records the supports ruling but three of its own references still name the withdrawn Protocol member
status: open
importance: low
importance_why: The authoritative ruling is present and correct in the same file, so nothing is blocked and no implementer can be misled for long — but one of the three is a revalidation trigger, and a trigger naming a symbol that cannot change is a trigger that can never fire.
effort: S
kind: inconsistency
area: training-load, .kiro/specs/training-load
created: 2026-07-26
surfaced_by: /kiro-queue — closing 2026-07-26-phase4-specs-pin-withdrawn-supports-member
pinned_at: 1efd0a4
resume_command: "do: repin training-load's own three remaining `LoadCalculator.supports` references onto the module-level supports_activity — design.md:292 (a revalidation trigger), design.md:682 (Req 1.14's traceability row) and tasks.md:34 — leaving design.md:812-820's ruling and design.md:479's historical diagram comment as they are [queue: .kiro/queue/2026-07-26-training-load-own-supports-references-not-repinned.md]"
context:
  - .kiro/specs/training-load/design.md
  - .kiro/specs/training-load/tasks.md
  - src/fitdocs/load/types.py
blocked_by: []
---

## What

`3121bb6` deleted the `supports` declaration from the `LoadCalculator` Protocol
and `training-load/design.md:812-820` records the full ruling — why a Protocol
member cannot carry a default body, why declaring it makes it mandatory under
`mypy --strict`, and why the seam is the module-level `supports_activity`
instead. That reasoning is correct and is the authority the sibling specs were
just repinned against.

Three references *in the same spec* were not moved with it:

1. `design.md:292` — a **revalidation trigger**: "`LoadCalculator.supports` is
   removed, the engine stops calling it before `collect_missing_fields`, or
   arbitration stops using it to narrow the no-default candidate set".
2. `design.md:682` — Req 1.14's traceability row names the artifact as
   `` `LoadCalculator.supports` ``.
3. `tasks.md:34` — "What it touches — `LoadContext`, `LoadCalculator.supports`,
   the `NotConfirmed` → `NotComputed` rename and the `ProfileView` purity rule".

Two further hits are **correct as they stand and should not be touched**:
`design.md:479`'s diagram comment and `design.md:812-820`'s ruling both describe
what Amendment 3 originally specified, deliberately, in the past tense.

## Why it matters

Low, and the reason it is not lower is `design.md:292`. A revalidation trigger
is a standing instruction to a future session: "if X changes, re-check Reqs 1.6,
1.14, 3.1 and 10.2". Its first clause now names a symbol that **has already been
removed and cannot be removed again**, so that clause can never fire. The real
trigger — the one that would genuinely invalidate `threshold-load`'s
Walk/Hike-through-`Modality.OTHER` declaration — is a change to
`supports_activity`'s resolution order, i.e. if it stopped preferring a
calculator's own `supports` over `supported_modalities` membership. Nothing
currently watches for that.

`design.md:682` is the row a reviewer sweeping Req 1.14 reads to find what
implements it, and it points at a member that does not exist.

Not high, because the correct ruling is present in the same document and a
reader who follows either reference will land on it within a page.

## Evidence

Verified at `1efd0a4`:

```
$ uv run python -c "from fitdocs.load.types import LoadCalculator; print(hasattr(LoadCalculator,'supports'))"
False

$ grep -rn "LoadCalculator.supports" .kiro/specs/training-load/
.kiro/specs/training-load/tasks.md:34
.kiro/specs/training-load/design.md:292    # revalidation trigger
.kiro/specs/training-load/design.md:479    # historical diagram comment - correct
.kiro/specs/training-load/design.md:682    # Req 1.14 traceability row
.kiro/specs/training-load/design.md:815    # the ruling itself - correct
```

The seam that replaced it: `supports_activity` at `src/fitdocs/load/types.py:378`,
with the rationale at `:18-35`.

`threshold-load` and `activity-qa-flags` were repinned by `a24fcdf`; that item
(`2026-07-26-phase4-specs-pin-withdrawn-supports-member`) was scoped to those
two specs by its own `resume_command`, which is why these three were left.

## How to pick it up

1. Read `design.md:812-820` first — it is the authority, and none of this
   changes it.
2. `design.md:292` is the substantive one. Do not merely rename the symbol:
   restate the trigger as the condition that can still occur. `a24fcdf` phrased
   the equivalent trigger in `threshold-load/design.md` as "**`supports_activity`'s
   resolution order changes** — if it stopped preferring a calculator's own
   `supports` over modality membership"; mirror that.
3. `design.md:682` and `tasks.md:34` are symbol swaps to `supports_activity`.
4. Leave `design.md:479` and `:812-820` alone — both are deliberate past-tense
   records of what Amendment 3 specified.

Done means: no `training-load` reference implies the Protocol member currently
exists, and every revalidation trigger names a change that can actually happen.
