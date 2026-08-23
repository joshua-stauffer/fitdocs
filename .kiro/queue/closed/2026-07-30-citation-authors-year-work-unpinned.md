---
id: 2026-07-30-citation-authors-year-work-unpinned
title: Citation.authors, .year and .work are falsifiable with the full suite green, one field over from the locators just pinned
status: done
importance: high
importance_why: The same defect class that justified pinning all six `locator` fields is live and unguarded on three sibling fields of the same records. A wrong author or year in a citation is a false provenance claim in the artifact whose entire purpose is inspectable provenance.
effort: S
kind: gap
area: load-channels, src/fitdocs/citation.py, src/fitdocs/load/channels/sources.py, tests/load/channels/test_sources.py
created: 2026-07-30
surfaced_by: adversarial review of chore/citation-locator-backstops (queue-tier1 batch)
pinned_at: c3d2201
resume_command: "do: decide whether Citation gets a whole-RECORD backstop rather than accumulating per-field ones, then pin authors/year/work accordingly in tests/load/channels/test_sources.py -- the per-field approach has now been applied twice (notes, then locators) and each round leaves the next field undefended [queue: .kiro/queue/2026-07-30-citation-authors-year-work-unpinned.md]"
context:
  - src/fitdocs/load/channels/sources.py
  - tests/load/channels/test_sources.py
  - src/fitdocs/citation.py
  - .kiro/queue/closed/2026-07-29-citation-locators-unpinned-and-undeclared.md
blocked_by: []
---

## What

`chore/citation-locator-backstops` added whole-value backstops to all six
`Citation.locator` fields in `src/fitdocs/load/channels/sources.py`, closing the
gap where a locator could be silently rewritten with the suite green.

Three sibling fields on the same records — `authors`, `year` and `work` — are
still guarded by nothing. They can be falsified with the full suite passing.

This is the second time this defect class has been closed one field at a time.
The `note` fields were pinned on 2026-07-29; the `locator` fields on
2026-07-30. Each round leaves the next field undefended, and each round is
prompted by a reviewer noticing the residual rather than by the mechanism
covering it.

## Why it matters

A `Citation` exists so a reader can go check a claim against the published work
it came from. `authors`, `year` and `work` are the fields that identify *which
work* — they are not decoration around the locator, they are the thing the
locator is an offset into.

A wrong year or a wrong author is a false provenance claim inside the artifact
whose entire purpose is inspectable provenance. Amendment 1's design review
warned specifically against "cheap escape hatches" that let a constant ship
under a weaker evidentiary status than claimed; an unpinned attribution is that
hatch left open on the identifying fields.

The queue item that closed the locator gap set the standard this one is judged
by: *"nothing in the module or the test file says these are unpinned, so a
session reading the test module sees six citations, a backstop mechanism, and
concludes the locators are covered."* That reasoning now applies verbatim to
`authors`/`year`/`work`, and with more force — a reader today sees six note
pins, six locator pins, and a test named
`test_every_citation_locator_is_pinned_by_a_backstop`.

## Evidence

Run by the reviewer against `chore/citation-locator-backstops` at `e2d2c40`,
each mutation applied to `MINETTI_2002` in
`src/fitdocs/load/channels/sources.py` and reverted afterwards:

```
MINETTI_2002.year     2002 -> 2003                                 -> 2297 passed  SURVIVOR
MINETTI_2002.authors  -> "Nobody, X."                              -> 2297 passed  SURVIVOR
MINETTI_2002.work     -> "Energy cost of swimming at extreme depths" -> 2297 passed  SURVIVOR
```

For contrast, on the same commit every one of the six `locator` fields reds on
mutation, each reddening exactly three tests, and a whitespace-only edit to a
locator also reds.

`MINETTI_2002` is the sharpest case because its `note` sources **both**
published polynomials to that record. If the `work` or `year` drifts, the note's
own attribution names a publication that does not contain what it claims — and
nothing reds.

The residual is declared in the test module as of the remediation round on that
branch, so this is a known and recorded gap rather than a silent one.

## How to pick it up

1. Read `tests/load/channels/test_sources.py` — `_LOCATOR_BACKSTOPS` and
   `test_every_citation_locator_is_pinned_by_a_backstop` are the per-field
   pattern, and the declared-residual block names exactly what is missing.
2. **Settle the design question before writing a third per-field mechanism.**
   The open question carried forward from the locator item is whether
   `Citation` should get a whole-**record** backstop — one pinned value per
   citation covering every field — instead of a fourth, fifth and sixth
   per-field dict. Three rounds of the same shape is the signal that the
   per-field approach is the wrong altitude. Read `src/fitdocs/citation.py` to
   see whether the record type can carry its own canonical form.
3. Whichever shape wins, the completeness guard matters more than the pins:
   assert the registry walk is non-empty, and assert set-equality between the
   citations and their backstops in **both** directions, so a seventh citation
   added without a backstop reds. The locator implementation does this
   correctly — copy it.
4. Done looks like: each of the three mutations above reds, a new `Citation`
   with an unpinned field reds, and no field of `Citation` remains both
   unpinned and undeclared.

## Open questions

- Whole-record backstop versus a third per-field dict — see step 2. This is the
  decision the locator item deferred, and deferring it again will produce the
  same finding a third time.
- Does `Citation.verification_status` want the same treatment? It is an enum
  rather than free text, so the falsification surface is narrower, but a record
  silently downgraded from `PRIMARY_TEXT` would be a provenance claim change
  that nothing catches.

## Resolution

**Closed `done` 2026-08-23 at `b4ccfa4`.** Fixed as a whole-record backstop, not a
third per-field dict — the shape the item's step 2 asked for.

`_ATTRIBUTION_BACKSTOPS` in `tests/load/channels/test_sources.py` pins a
fingerprint over every field of `Citation` that has no dedicated pin, deriving
that field list by walking `dataclasses.fields(Citation)` rather than naming
the fields. Consequences, which is why this shape was chosen: adding a field to
`Citation` reds all six backstops, and removing a dedicated pin drops that
field back into the fingerprint and reds too. A field cannot ship both unpinned
and undeclared, so the "next field left undefended" cycle this item was filed
against cannot run a fourth time.

Rendering is plain values rather than `repr`, so a reviewer can read a
fingerprint against `sources.py` directly.

The item's second open question is answered rather than deferred:
`verification` renders as its enum `.value`, so a record silently downgraded
from `PRIMARY_TEXT` now reds.

Measured discrimination (38 tests in the module), each mutation applied and
reverted:

- `MINETTI_2002.year` 2002 -> 2003 — red (was green)
- `MINETTI_2002.authors` -> "Nobody, X." — red (was green)
- `MINETTI_2002.work` -> another title — red (was green)
- `MINETTI_2002.verification` -> `SECONDARY_ATTESTATION` — reds 4
- adding a field to `Citation` — reds 1 (all six comparisons)
- misspelling a `_DEDICATED_FIELD_PINS` entry — reds 2
- widening `_DEDICATED_FIELD_PINS` to include `authors` — reds 1

Suite: 2459 passed, 5 skipped; ruff and mypy --strict clean.
