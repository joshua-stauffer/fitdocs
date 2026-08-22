---
id: 2026-07-27-trimp-weighting-default-is-sex-named
title: fit-ingest Req 17 is about sex, design.md never says so, and 17.2 forces a default that reports every athlete under the male weighting
status: done
importance: high
importance_why: Req 17.2 plus the now-read primary text jointly determine that DerivedMetrics.trimp_weighting reports the male selection for every athlete who states nothing — a user-facing labelling decision currently deferred to an implementer as an enum-naming detail, in a spec whose design approval is the open gate.
effort: S
kind: spec-work
area: fit-ingest, .kiro/specs/fit-ingest/design.md
created: 2026-07-27
surfaced_by: /kiro-validate-design fit-ingest
pinned_at: 28afa75
resume_command: "/kiro-spec-design fit-ingest [queue: .kiro/queue/2026-07-27-trimp-weighting-default-is-sex-named.md] Fix TrimpWeighting's members and default in the design, and record the sex-neutral application as a DEPARTURES entry"
context:
  - .kiro/specs/fit-ingest/design.md
  - .kiro/specs/fit-ingest/requirements.md
  - docs/reference/banister-trimp-primary-sources.md
  - .kiro/queue/2026-07-27-banister-morton-primary-texts-obtained.md
  - src/fitdocs/metrics/types.py
  - src/fitdocs/metrics/stress.py
blocked_by: []
---

## What

fit-ingest Req 17 ("Selectable Training-Impulse Weighting") opens: "As an athlete
**whose sex** the training-impulse model distinguishes, I want TRIMP computed
with the weighting terms its source specifies for me."

`design.md` — the document that implements Req 17 — does not contain the word
*sex*, *male*, or *female* anywhere. It defers `TrimpWeighting`'s member set
entirely to implementation and hedges over whether the cited text assigns the
pre-amendment pair to a named selection.

That is now settled by the primary text, and the consequence follows
mechanically:

- Banister 1991 p. 408 defines two selections: male `(0.64, 1.92)` and female
  `(0.86, 1.67)`. So the text *does* name the selection.
- Req 17.2 pins the default to the pair applied before Amendment 1 — `(0.64,
  1.92)`, which `stress.py` ships today.
- Therefore `DEFAULT_TRIMP_WEIGHTING` is necessarily the **male** member, and
  Req 17.6 requires that selection be reported alongside every TRIMP value.

So every activity computed without an explicit per-call selection will report
`DerivedMetrics.trimp_weighting` as the male selection. Req 17.3 forbids reading
the selection from stored athlete profile data or any configuration file, so no
downstream spec can remember an athlete's selection between calls — the default
is what fires in practice, for everyone.

Separately, Req 16.5 requires a deliberate departure from the cited work to be
recorded with its reason. The primary-text reading confirmed that applying the
sex-specific male pair sex-neutrally is a real deviation from **both** texts, not
a sourcing artifact. `design.md` specifies the `Departure` type and a `DEPARTURES`
tuple but names no entry for it.

## Why it matters

Two distinct things, both worth a maintainer's eyes rather than an implementer's
default:

1. **What the document says.** `trimp_weighting` is a reported field. Req 17.6's
   stated purpose is that "two athletes' training-impulse numbers are never
   compared without that distinction being visible" — and the visible value will
   read as the male selection for every athlete who supplied nothing, including
   athletes for whom the model defines a different pair. How that renders (and
   what it is called) is a product decision with a real user-facing edge.
2. **What the record says.** The sex-neutral collapse is the single clearest
   `Departure` this amendment has, it is now attested against both primary texts,
   and it is missing from the design's `DEPARTURES` content. Amendment 1's own
   rationale already flagged that resolving the primary text "is a different
   reported number for some athletes"; that sentence is now backed by page
   citations and still has no record to land in.

Leaving both to the sourcing task means an implementer names an enum member and
picks a default with a sex in its name, under time pressure, inside a task whose
stated boundary is citation bookkeeping.

## Evidence

Verified on `main` at `28afa75`:

- `grep -n "sex\|male\|female" .kiro/specs/fit-ingest/design.md` → **zero
  matches** (84 KB document).
- `.kiro/specs/fit-ingest/requirements.md`, Req 17 Objective — "As an athlete
  whose sex the training-impulse model distinguishes…"
- `.kiro/specs/fit-ingest/requirements.md`, 17.2 — default is "the weighting pair
  it applied before Amendment 1"; 17.3 — "caller-supplied input only, and shall
  not read it from stored athlete profile data or from any configuration file";
  17.6 — report which pair produced the value.
- `.kiro/specs/fit-ingest/design.md:1067-1070` — `TrimpWeighting`'s body is a
  docstring only: "Members are fixed by the sourcing task from the primary text."
- `.kiro/specs/fit-ingest/design.md:984-992` — the `DEFAULT_TRIMP_WEIGHTING`
  hedge: "if the text assigns that pair to a named selection, the default *is*
  that selection; if it assigns it to none, a distinctly named member carries
  it." The text assigns it: male.
- `docs/reference/banister-trimp-primary-sources.md:59-66` — `y = 0.64·e^(1.92x)`
  (male) / `y = 0.86·e^(1.67x)` (female), p. 408.
- `docs/reference/banister-trimp-primary-sources.md:304-308` — §6 "Deviations of
  fitdocs' shipped implementation from the sources", item 2 "Sex-neutral use of
  the male exponent": "Both sources define b per sex (1.92 / 1.67). fitdocs
  applies 1.92 to every athlete. This is now confirmed as a genuine deviation
  from both primary texts, not an artifact of secondary sourcing."
- `src/fitdocs/metrics/stress.py:55-58` — `_TRIMP_COEFFICIENT = 0.64`,
  `_TRIMP_EXPONENT = 1.92`, the pre-amendment pair Req 17.2 defaults to.
- `.kiro/specs/fit-ingest/design.md:686-692, 1034` — `Departure` type and
  `DEPARTURES: Final[tuple[Departure, ...]]` exist; the design specifies no
  entry for the sex-neutral application. `grep -n "DEPARTURES" design.md` returns
  only type/interface/guard references, no content.

Not established by this review: what the maintainer wants the members called, or
how `workout-docs` should render an unstated selection. Those are the decisions
this item exists to surface, not to pre-empt.

## How to pick it up

1. Read Req 17 in `.kiro/specs/fit-ingest/requirements.md` in full (six criteria,
   ~10 lines), then `design.md:984-992` and `:1067-1070` — that is the entire
   proposed treatment.
2. Read `docs/reference/banister-trimp-primary-sources.md` §1 "Weighted form"
   (the p. 408 extraction, `:59-66`) and §6 item 2 (`:304-308`) for the
   sex-specific-vs-collapsed finding. §6 items 1 and 3 list the other two
   confirmed deviations, which may also want `DEPARTURES` entries — check
   whether they are in scope for Amendment 1 before adding them.
3. Fix the member set and the default **in the design** rather than deferring
   them: `TrimpWeighting` has the two members the text defines, and
   `DEFAULT_TRIMP_WEIGHTING` is whichever carries `(0.64, 1.92)`. Get the
   maintainer's explicit sign-off on the member **names** — this is the decision
   the item is filed for.
4. Add the `DEPARTURES` entry Req 16.5 requires: subject = the sex-neutral
   application of a sex-specific weighting; `source_specifies` = per-sex terms
   (B91 p. 408, M90 p. 1172); `fitdocs_does` = applies the male pair to every
   athlete absent a selection; `reason` = the maintainer's, recorded verbatim.
5. Decide and record what `workout-docs` renders for `trimp_weighting` when the
   caller selected nothing. This is a cross-spec consequence: fit-ingest reports
   the field, workout-docs displays it, and 17.3 guarantees nothing remembers the
   athlete's answer between runs. If the answer is "workout-docs renders nothing
   unless the selection was explicit," say so in the design's boundary section so
   the downstream spec is not left to infer it.
6. Verify Req 17.2's regression test is still expressible after the rename: the
   design's Testing Strategy §11 (`design.md:1447-1453`) requires that "no
   selection reproduces the pre-amendment TRIMP value exactly" — that test is the
   proof no athlete's number moved, and it must pin the *value*, not the member
   name, so a later rename cannot silently weaken it.

Done looks like: `design.md` names the two selections and the default, carries a
`DEPARTURES` entry for the sex-neutral application, and records what a document
shows when the athlete stated nothing. Design-document edit only — `TrimpWeighting`
does not exist in `src/fitdocs/metrics/types.py` yet (verified at `28afa75`).

## Resolution

Closed 2026-07-29. Resolved by the fit-ingest Amendment 1 design revision at
the gate (`a6418a7`). `.kiro/specs/fit-ingest/design.md:1118-1130` now names
the `TrimpWeighting` members explicitly, states that
`DEFAULT_TRIMP_WEIGHTING` is `BANISTER_MALE` "and that is a consequence, not
a preference" (Req 17.2 pins the no-selection default to the pair applied
before Amendment 1, `stress.py:55-58`'s `(0.64, 1.92)`, which is B91's male
curve), and says plainly that by Req 17.6 this is what
`DerivedMetrics.trimp_weighting` reports for every athlete supplying no
selection. The sex-neutral application is recorded in `DEPARTURES` as
`trimp-weighting-sex-neutral-default` (Req 16.5), which is the second half
the item asked for. design.md:1109-1110 also flags it for the maintainer as
a presentation-adjacent choice rather than burying it in an enum.
