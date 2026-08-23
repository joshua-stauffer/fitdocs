---
id: 2026-07-27-threshold-load-research-walking-form-stale
title: threshold-load/research.md still says Minetti's walking polynomial "was not obtained"
status: open
importance: low
importance_why: A falsified provenance claim left standing in a spec's research record; nothing computes from it, but it is the sixth copy of a claim the other five were corrected for, and research.md carries no per-finding dates so it reads as a live finding.
effort: S
kind: inconsistency
area: threshold-load, .kiro/specs/threshold-load/research.md
created: 2026-07-27
surfaced_by: /kiro-queue close 2026-07-26-citation-vocabulary-diverges-across-layers
pinned_at: c3d2201
resume_command: "do: correct .kiro/specs/threshold-load/research.md:108 — Minetti's walking polynomial WAS obtained (Fig. 1's caption in the read primary text gives both regressions); the walking form is unimplemented by scope choice, not unavailability. Apply the same dated 'Superseded 2026-07-27' amendment parenthetical already used in load-channels' requirements.md:252, tasks.md and research.md [queue: .kiro/queue/2026-07-27-threshold-load-research-walking-form-stale.md]"
context:
  - .kiro/specs/threshold-load/research.md
  - .kiro/specs/load-channels/requirements.md
  - src/fitdocs/load/channels/sources.py
blocked_by: []
---

## What

`.kiro/specs/threshold-load/research.md:108` reads, in a bullet about
anchoring Walk/Hike:

> `load-channels` returns `MODEL_NOT_DEFINED` for pace on any non-running
> modality (Minetti's walking polynomial was not obtained)

The parenthetical is false as of `chore/citation-vocabulary-unify`. Re-sourcing
`MINETTI_2002` to `PRIMARY_TEXT` read Fig. 1's caption in the publisher-typeset
PDF, which gives **both** the running and the walking 5th-order regressions
verbatim. The walking form is unimplemented because of a scope decision, not
because the source was unobtainable.

Five other copies of this same claim were found and corrected under
`.kiro/queue/closed/2026-07-26-citation-vocabulary-diverges-across-layers.md`
(`load-channels/requirements.md` Req 7.9, its `research.md:107-108` and
`:317`, `tasks.md`, and `design.md`'s traceability row). This sixth copy was
deliberately left unedited because it sits in a different spec, outside that
branch's boundary — flagged in that item's body, but never queued in its own
right, so closing that item would have retired the only record of it.

## Why it matters

Not a correctness bug: no number changes and no test fails. It is the same
provenance-record class the citation vocabulary exists to prevent — a reader
auditing why the walking form is missing gets "the source was not obtainable",
which would send them off to obtain a text that has in fact been read. The
conclusion (Walk/Hike pace is `MODEL_NOT_DEFINED`) is unaffected; only its
stated reason is wrong.

`research.md` carries no per-finding date stamps, so there is nothing in the
file to signal the claim is superseded. That is precisely why the other five
copies got an explicit dated parenthetical rather than a silent edit.

## Evidence

Verified on `main` at `4a5c838`:

- `.kiro/specs/threshold-load/research.md:108` — the stale parenthetical,
  unamended and undated.
- `.kiro/specs/load-channels/requirements.md:252` — Req 7.9, the same claim
  corrected, with the amendment parenthetical to copy the form from: "though
  it was read in the same source used for the running form, was not
  implemented — a scope decision, not a sourcing gap".
- `src/fitdocs/load/channels/sources.py` — `MINETTI_2002` carries
  `VerificationStatus.PRIMARY_TEXT`.

## How to pick it up

1. Read `load-channels/requirements.md:252` for the exact wording and the
   dated-parenthetical form already ratified for this correction.
2. Amend `threshold-load/research.md:108`'s parenthetical to state the scope
   reason, with a `_(Superseded 2026-07-27, queue
   2026-07-27-threshold-load-research-walking-form-stale: …)_` note so a reader
   can see when the original finding stopped being true.
3. Do **not** change the surrounding conclusion — `MODEL_NOT_DEFINED` for pace
   on non-running modalities is still correct, and the anchor-map implication
   below it is unaffected.
4. Grep `threshold-load/` for any other copy before finishing; five of six
   copies were found one at a time in earlier rounds.
5. Trivial-class change per `change-protocol.md` (spec prose, no `src/`, no
   `tests/`) — but it is spec prose, not a typo, so triage it explicitly
   rather than assuming.
