---
id: 2026-07-26-phase4-specs-pin-withdrawn-supports-member
title: threshold-load and activity-qa-flags still spec the withdrawn `supports` Protocol member, including an unsatisfiable hard prerequisite
status: done
importance: high
importance_why: threshold-load's spec.json and tasks.md record a HARD PREREQUISITE on a Protocol member that was permanently withdrawn by 3121bb6; threshold-load is on the critical path for fitdocs computing any load at all, so it cannot be implemented as written.
effort: M
kind: inconsistency
area: threshold-load, activity-qa-flags, .kiro/specs/
created: 2026-07-26
surfaced_by: /kiro-queue sweep — round-2 review of the roadmap tick (queue item 2026-07-25-wiki-contract-load-keys-landed)
pinned_at: 17ff340
resume_command: "do: repin threshold-load and activity-qa-flags onto the module-level supports_activity(calculator, activity) — LoadCalculator declares no supports member and never will (src/fitdocs/load/types.py:18-35). Start with threshold-load/tasks.md:39 and spec.json's phase_note, both of which record an unsatisfiable hard prerequisite [queue: .kiro/queue/2026-07-26-phase4-specs-pin-withdrawn-supports-member.md]"
context:
  - .kiro/specs/threshold-load/design.md
  - .kiro/specs/threshold-load/tasks.md
  - .kiro/specs/threshold-load/requirements.md
  - .kiro/specs/threshold-load/spec.json
  - .kiro/specs/activity-qa-flags/design.md
  - src/fitdocs/load/types.py
blocked_by: []
---

## What

`training-load` Amendment 3 planned to add `supports(activity)` to the
`LoadCalculator` Protocol. During implementation that clause was **reversed on
measured grounds** and the declaration was deleted by commit `3121bb6`
("remove the Protocol supports declaration the drift closure missed").

The reversal was applied to `training-load/design.md` only. The closed queue
item that drove it — `.kiro/queue/closed/2026-07-26-supports-call-shape-design-drift.md`
— is scoped to that single file by its own `resume_command`. Two other Phase 4
specs recorded the same ruling and were never repinned.

Ground truth in the shipped tree:

- `LoadCalculator.__dict__` is `{compute, required_athlete_fields}` plus the
  annotations `calculator_id`, `display_name`, `supported_modalities`.
  `hasattr(LoadCalculator, "supports")` is `False`.
- The sport-support gate is the module-level
  `supports_activity(calculator, activity)` at `src/fitdocs/load/types.py:378`,
  which getattr-detects a calculator's *optional, off-Protocol* `supports` and
  otherwise falls back to `supported_modalities` membership.
- Rationale at `src/fitdocs/load/types.py:18-35`: declaring `supports` on the
  Protocol makes it **mandatory for structural conformance under
  `mypy --strict`**, and three of four stub calculators plus the installed
  plugin fixture answer `hasattr(cls, "supports") == False` — they would raise
  `AttributeError` the first time the engine's gate called it.

## Why it matters

`threshold-load` is the spec that makes fitdocs compute any load at all — with
the withdrawn methodology gone it is the only built-in calculator, and the roadmap puts it on
Phase 4's critical path. It currently **cannot be implemented as written**:

- `.kiro/specs/threshold-load/tasks.md:39` — "**Hard prerequisite for task
  3.3**: `LoadContext` and the `supports` protocol member. Without them there
  is no way to reach the configuration or to refuse an activity before the
  prompt flow." `LoadContext` landed; the `supports` member never will.
- `.kiro/specs/threshold-load/spec.json` `phase_note` ends: "NEW HARD
  PREREQUISITE: LoadContext and the supports protocol member must land in
  training-load before task 3.3." That prerequisite is now permanently
  unsatisfiable, and it is recorded in the file `/kiro-spec-status` reads.

An implementer picking up task 3.3 will either block on a member that will
never arrive, or add it — re-landing exactly the drift `3121bb6` deleted, which
would break structural conformance for every existing stub and the installed
plugin fixture.

The fix is genuinely small (the *capability* survives — a calculator may still
define `supports`; it is simply optional and off-Protocol, which is what
`threshold-load` Req 2.7 actually wants). The cost is entirely in it being
discovered at implementation time instead of now.

Note `threshold-load/design.md:184` already carries this as an anticipated
risk — "**The `LoadCalculator` protocol's `supports` member changes or is
withdrawn**". The risk materialised; nothing updated the spec.

## Evidence

Verified at `17ff340`:

```
$ uv run python -c "from fitdocs.load.types import LoadCalculator; print(hasattr(LoadCalculator,'supports'))"
False
```

Live sites still asserting the Protocol member:

- `.kiro/specs/threshold-load/requirements.md:78` — "**The calculator contract
  gains `supports(activity)`**, asked by the load..."
- `.kiro/specs/threshold-load/tasks.md:11`, `:30`, `:39` (the hard prerequisite)
- `.kiro/specs/threshold-load/design.md:23`, `:87`, `:111` ("including the
  `supports` member added by `training-load` Amendment 3"), `:184`, `:239`,
  `:411`, `:415`, `:450`, `:666`
- `.kiro/specs/threshold-load/design.md:209` — asset table row:
  `` | `LoadCalculator.supports(activity)` | `training-load` (Amendment 3, task 4.1) | ``
- `.kiro/specs/threshold-load/spec.json:7` — `phase_note`, ruling (5) and the
  closing "NEW HARD PREREQUISITE" sentence
- `.kiro/specs/activity-qa-flags/design.md:62` — "`LoadCalculator` gains
  `supports(activity)`, asked before the prompt flow"

`load-channels` is **not** affected: `grep -rc LoadCalculator .kiro/specs/load-channels/*.md`
returns 0 everywhere except `design.md` (1 incidental mention). It implements
no calculator — it is the pure per-channel math.

## How to pick it up

1. Read `src/fitdocs/load/types.py:18-35` and `:378-407` first. The capability
   still exists; only its *location* changed. `threshold-load` Req 2.7 wants a
   calculator that answers `activity.sport in SUPPORTED_SPORTS` before the
   prompt flow — that still works, as an optional `supports` method the
   module-level `supports_activity` will find by `getattr`.
2. Start with the two files that record an unsatisfiable obligation, because
   they are what will actually block an implementer:
   `.kiro/specs/threshold-load/tasks.md:39` and `spec.json`'s `phase_note`.
   Restate the prerequisite as `LoadContext` alone — which has landed — and
   note `supports` is optional and off-Protocol.
3. Then sweep `threshold-load/design.md` (ten sites) and
   `requirements.md:78`. `design.md:209`'s asset table is the important one:
   it attributes the member to `training-load` task 4.1, which is a
   cross-spec claim that is now false in both directions.
4. `activity-qa-flags/design.md:62` is a one-line fix.
5. `design.md:184`'s risk row should be closed out as MATERIALISED with the
   resolution, rather than left as a pending risk.

Done means: no Phase 4 spec asserts `LoadCalculator` has a `supports` member;
`threshold-load`'s hard prerequisite names only things that exist; and
`/kiro-spec-status threshold-load` reads clean.

## Open questions

- Does repinning `requirements.md:78` (a numbered criterion) need
  re-approval, or is it an in-place correction like the ones `training-load`
  recorded in `spec.json`'s `phase_note`? The criterion's *intent* (the engine
  asks before the prompt flow) is unchanged and still shipped — only the
  mechanism moved — which argues for in-place.


## Resolution

**Done 2026-07-26** — `a24fcdf`, branch `chore/queue-top-ten`.

Verified `hasattr(LoadCalculator, "supports")` is `False`.

Recorded as `threshold-load/design.md` Amendment 2 and applied across the ten
design sites, the three `tasks.md` sites, `requirements.md`'s Amendment 1
narrative, `spec.json`'s ruling (5) and its prerequisite sentence, and
`activity-qa-flags/design.md`'s one line. The anticipated risk row "the
`supports` member changes or is withdrawn" is closed out as MATERIALISED with
its resolution and replaced by the live trigger (`supports_activity`'s
resolution order).

The capability was never lost -- only relocated to the module-level
`supports_activity`, so `ThresholdCalculator.supports` is still written exactly
as designed and Req 2.7 is untouched.

Open question resolved: **no re-approval needed, and no criterion changed.**
Criterion 2.7 is mechanism-neutral as written ("when the load pass asks whether
a given activity is supported"), so only the Amendment narrative around it
needed correcting, in place.
