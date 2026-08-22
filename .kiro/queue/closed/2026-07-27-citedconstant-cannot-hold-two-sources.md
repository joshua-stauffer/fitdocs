---
id: 2026-07-27-citedconstant-cannot-hold-two-sources
title: fit-ingest design.md's `CitedConstant` holds exactly one source, so Req 15.2's two works with per-work locators are unrepresentable
status: done
importance: high
importance_why: An approved acceptance criterion has no mechanism in the design that is meant to implement it, at a spec whose design approval is the open gate — and the primary texts have since been read and found to disagree, so the record this design cannot express is now the record the evidence actually requires.
effort: S
kind: gap
area: fit-ingest, .kiro/specs/fit-ingest/design.md
created: 2026-07-27
surfaced_by: /kiro-validate-design fit-ingest
pinned_at: 28afa75
resume_command: "/kiro-spec-design fit-ingest [queue: .kiro/queue/2026-07-27-citedconstant-cannot-hold-two-sources.md] Give CitedConstant a way to record Req 15.2's two works with per-work locators, and add the missing 15.2 guard"
context:
  - .kiro/specs/fit-ingest/design.md
  - .kiro/specs/fit-ingest/requirements.md
  - docs/reference/banister-trimp-primary-sources.md
  - .kiro/queue/closed/2026-07-27-trimp-coefficient-b91-vs-m90.md
  - .kiro/queue/2026-07-27-banister-morton-primary-texts-obtained.md
  - src/fitdocs/load/channels/sources.py
blocked_by: []
---

## What

fit-ingest Req 15.2 requires that a training-impulse weighting term "record
Banister (1991) **and** Morton (1990) as its sources, together with the locator
within each work at which the value appears."

The design that implements Amendment 1 gives a constant exactly one source and
says so as a deliberate invariant. There is no field, tuple, or second record
reference in which the *second* work and *its* locator can live, and no guard
asserts 15.2 at all. The requirement is traceable to two module-level names
that nothing binds to a constant.

This is not a naming quibble. Amendment 1 exists to move citation out of
docstring prose into a typed, guard-enforced record; under the design as
written, "Morton 1990 Eq. 2 p. 1172 prints this weighting with no coefficient"
can only be recorded in `Citation.note` free text — the exact artifact the
amendment was created to eliminate.

## Why it matters

When the design was drafted (2026-07-26) both primary texts were believed
unobtainable, so what a two-source record would have to *say* was unknown and
the single-source shape looked sufficient. Both texts have since been read in
full and they disagree:

- Banister 1991 p. 408: `y = 0.64·e^(1.92x)` (male) / `0.86·e^(1.67x)` (female)
- Morton 1990 Eq. 2 p. 1172: `Y = e^(bx)`, b = 1.92 / 1.67, **no multiplicative
  coefficient at all**

The maintainer ruled 2026-07-27 to keep `0.64`. So the coefficient's record must
now state, machine-readably: which work fixes the value, which companion primary
text omits it, the locator in each, and which form fitdocs ships. The closed
coefficient item hands exactly that obligation forward — and flags that
`VerificationStatus` has no term for "primary text, but a companion primary text
disagrees," leaving open whether `PRIMARY_TEXT` plus a note suffices. The design
does not decide it.

Requirements 15.2 and 16.2 ("exactly one such record") are in tension with each
other, and the design resolved that tension silently in favour of 16.2. That
choice may well be the right one, but it should be a recorded design decision
with 15.2's per-work locators explicitly accounted for, not an unremarked
casualty of the type signature.

## Evidence

Verified on `main` at `28afa75`:

- `.kiro/specs/fit-ingest/design.md:648-649` — "`CitedConstant` is the binding
  required by 16.2. It carries exactly one `source`, so a constant with two
  sources or none cannot be constructed."
- `.kiro/specs/fit-ingest/design.md:699` — `source: SourceRecord`, where
  `SourceRecord = Citation | FitdocsChoice` (`:684`). Singular.
- `.kiro/specs/fit-ingest/design.md:434` — traceability records 16.2's interface
  as "`CitedConstant.source` (single-valued)".
- `.kiro/specs/fit-ingest/design.md:425` — the only substantive mention of 15.2
  in the whole document: a traceability row naming `BANISTER_1991` and
  `MORTON_1990` with no stated binding to any constant. `grep -n "15\.2"
  design.md` returns only this line and `:1437` (a "locator is non-empty"
  assertion, which does not carry the two-works obligation).
- `.kiro/specs/fit-ingest/design.md:1319-1323` — ConstantGuard's registry
  assertions, enumerated. 15.2 is absent from the list; the component's own
  Requirements field (`:1310`) reads "15.4, 15.5, 15.6, 15.7, 16.2, 16.3".
- `docs/reference/banister-trimp-primary-sources.md:59-66, 85-96, 195-196` —
  the two forms and the explicit finding "B91 carries `0.64` (male) / `0.86`
  (female); M90 Eq. 2 has no leading coefficient at all. Both agree exactly on
  the exponents 1.92 / 1.67."
- `docs/reference/banister-trimp-primary-sources.md:303` — "Ruled 2026-07-27:
  this is the intended form and stays."
- `.kiro/queue/closed/2026-07-27-trimp-coefficient-b91-vs-m90.md` — Resolution
  hands forward that the citation note must name both forms and that
  `VerificationStatus` has no term for a conflict between primary sources.
- Existing precedent for how bad the prose route gets:
  `src/fitdocs/load/channels/sources.py:186-240` — the `BANISTER_TRIMP` record,
  55 lines, of which the `note` is ~45. It is where the multi-source narrative
  currently lives, and it carries `locator=None`.

Not yet checked by this review: whether any *other* constant in the 15.6
enumeration also has more than one defining work. Only the weighting terms are
named by 15.2.

## Why this is not the Banister re-sourcing item

`.kiro/queue/2026-07-27-banister-morton-primary-texts-obtained` owns the
`VerificationStatus` **vocabulary** decision (it now carries two flagged gaps:
the primary-source conflict, and the split attestation where the chapter content
is primary text but the 1991 publication year comes from the OCLC/Internet
Archive catalogue record because the book's copyright page carries no year). It
also owns flipping `BANISTER_TRIMP` in `load-channels`.

This item is the distinct, unowned problem one layer over: fit-ingest's
`design.md` proposes a record **shape** that cannot hold what either decision
concludes. Note that the same shape pressure shows up in `Citation.year: int`
being a required, non-optional field for a datum no primary text attests — same
cause, and worth resolving in one pass, but the vocabulary ruling belongs to the
other item.

## How to pick it up

1. Read `.kiro/specs/fit-ingest/requirements.md` criteria 15.2, 16.1, 16.2, 16.4
   and 16.5 together, then `design.md`'s "citation layer" section
   (`:627-711`) — that is the whole proposed vocabulary, about 80 lines.
2. Read `docs/reference/banister-trimp-primary-sources.md` §D1 and §D1a for what
   the record has to be able to say. The short version: two works, agreeing
   exponent, disagreeing coefficient, ruling in favour of the coefficient, and
   Morton's own worked example implying the coefficient his equation omits.
3. Decide the shape. Two candidates, and this is a maintainer call:
   - **Typed corroborators.** Keep one governing `source` (so 16.2's "exactly
     one record" survives) and add
     `corroborators: tuple[Corroboration, ...]`, each carrying work, locator,
     and an agreement verdict (`agrees` / `omits` / `differs`). 15.2 then
     becomes a guard assertion rather than prose, and the primary-source
     conflict is queryable instead of narrated.
   - **`PRIMARY_TEXT` plus a prose note**, accepting that 15.2's per-work
     locators stay unstructured. Cheaper; record it as an explicit design
     decision naming what is given up, so the next reviewer does not re-find it.
4. Whichever is chosen, add the missing guard: every constant that is a term of
   the training-impulse weighting names both works, each with a non-empty
   locator. Put it in the ConstantGuard registry assertions
   (`design.md:1319-1323`) and in the component's Requirements field.
5. Update the traceability row at `design.md:425` so 15.2 points at a mechanism
   rather than at two unbound names.
6. Coordinate with `2026-07-27-banister-morton-primary-texts-obtained` before
   writing — it owns the vocabulary ruling this shape has to hold, and doing
   both in one pass avoids a second design gate.

Done looks like: `design.md` states how 15.2's two works and two locators are
recorded, a guard asserts it, and the 15.2 ↔ 16.2 tension is a recorded decision
rather than an unremarked one. This is a design-document edit — no `src/` change
is needed to close it, since `citation.py` and `metrics/sources.py` do not exist
yet (verified at `28afa75`).

## Resolution

Closed 2026-07-29. Resolved by the fit-ingest Amendment 1 design revision at
the gate (`a6418a7`). `.kiro/specs/fit-ingest/design.md` now carries the
`Corroboration` and `Agreement` types and `CitedConstant.corroborators`
(design.md:103-106), and design.md:692 records why `corroborators` satisfies
Req 15.2 without breaking Req 16.2. The missing 15.2 guard the item named is
now in the traceability table at design.md:464, which reads: "Weighting terms
cite Banister (1991) *and* Morton (1990) with locators | CitationVocabulary,
MetricsSources, ConstantGuard | `Corroboration`, `Agreement`,
`CitedConstant.corroborators`; guard asserts both works with per-work
locators".

Scope note: this closes the DESIGN gap the item raised, which is what its
`resume_command` (`/kiro-spec-design fit-ingest`) asked for. The
implementation of that guard is fit-ingest task work.

## Resolution, part 2 — implementation verification

_Both this section and the one above were written independently: the design-gate
close by the `queue-top7` session on `main`, this one by `impl-fit-ingest` during
task 9.3. They agree and are kept together rather than one replacing the other,
since they verify different things — that the design gap closed, and that the
shape it specified is now shipping code._

Closed as **done**: the design was regenerated under Amendment 1 and took
option (a), typed corroborators. Every "done looks like" criterion is met.
Verified on `impl/fit-ingest` at `a34d8f6`:

- **The shape exists and is built.** `design.md:758` declares `Corroboration`
  (work, `locator`, `agreement`, `note`); `:778`
  `corroborators: tuple[Corroboration, ...] = ()` on `CitedConstant`; `:752`
  the `Agreement` enum (`AGREES` / `OMITS` / `DIFFERS`). All three are shipping
  code, not just design: `src/fitdocs/citation.py:129-159, 179-199` (landed in
  task 8.1).
- **The 15.2 ↔ 16.2 tension is a recorded decision, not an unremarked
  casualty.** `design.md:692-706` states it explicitly — "Those read as a
  contradiction only if 'record' and 'governing source' are the same thing" —
  names the rejected alternative (one `Citation` plus a prose `note`) and why
  it was rejected (unstructured, so the second locator fails 16.1's
  machine-readable bar). Recorded as Decision D6 in `research.md`.
- **The missing guard is specified.** `design.md:785-789`: every
  `Corroboration` has a non-empty `locator`, and a non-`None` `note` whenever
  `agreement` is not `AGREES`; no `Corroboration` names the same work as its
  constant's governing `source`. Asserted by ConstantGuard so the failure names
  the offending constant. `design.md:1197` additionally requires each weighting
  term to carry its corroborator with a non-empty locator.
- **The traceability row points at a mechanism.** `design.md:464` now reads
  "`Corroboration`, `Agreement`, `CitedConstant.corroborators`; guard asserts
  both works with per-work locators" — previously two unbound names.

The item's own note that "no `src/` change is needed to close it, since
`citation.py` and `metrics/sources.py` do not exist yet" is superseded: both
now exist and already carry the shape.

Two pieces of the original item are **not** closed here and are owned
elsewhere, as the item itself anticipated:

- The `VerificationStatus` vocabulary question (no term for "primary text, but a
  companion primary text disagrees", and the split attestation on
  `Citation.year`) remains open at
  `.kiro/queue/2026-07-27-banister-morton-primary-texts-obtained.md`.
  `design.md:707-710` explicitly scopes it out: "What `corroborators` does *not*
  solve … one *field* of this citation is attested differently from the rest."
- Building the guard is task 12.1; *populating* the corroborators is task 9.3,
  in progress at close time. Closing this item records that the design gap is
  gone, not that the guard is written.

