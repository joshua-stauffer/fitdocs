---
id: 2026-07-29-citation-locators-unpinned-and-undeclared
title: Five of six Citation.locator fields carry evidence claims that can be falsified with the suite green
status: done
importance: high
importance_why: The notes are now whole-value pinned but the locators beside them are not, so the page, figure, edition and volume a reader would use to check a citation can be silently wrong. Two were falsified with 2098 tests passing. MINETTI's is load-bearing — its note sources both polynomials to that exact Fig. 1 caption.
effort: S
kind: gap
area: load-channels, src/fitdocs/load/channels/sources.py, tests/load/channels/test_sources.py
created: 2026-07-29
surfaced_by: adversarial review of chore/banister-resource-and-note-backstops (queue-top7 batch)
pinned_at: 421c075
resume_command: "do: add whole-value backstops for the remaining five Citation.locator fields in tests/load/channels/test_sources.py, matching BACKSTOP_BANISTER_TRIMP_LOCATOR — or, if any is deliberately left unpinned, declare that residual in the test module with the mutation that proves it [queue: .kiro/queue/2026-07-29-citation-locators-unpinned-and-undeclared.md]"
context:
  - src/fitdocs/load/channels/sources.py
  - tests/load/channels/test_sources.py
  - .kiro/queue/closed/2026-07-28-load-channel-citation-notes-unpinned.md
blocked_by: []
---

## What

The 2026-07-29 change added whole-value equality backstops to all six
citation `note` fields, and a `BACKSTOP_BANISTER_TRIMP_LOCATOR` for the one
`locator` it introduced. The other five `locator` fields are guarded only by
`assert ... is not None` — the named **vacuous introspection** anti-pattern in
`.kiro/steering/change-protocol.md`.

A `locator` is the same class of artifact as a `note`: it is the page, figure,
equation, edition or volume a reader uses to go check the claim. Pinning the
prose that describes a source while leaving the pointer to that source
free-floating covers the smaller half.

## Why it matters

This is the residual of a defect class that was already confirmed live. The
`note` backstops exist because an independent reviewer found 21 falsifiable
claims in fit-ingest's three notes, and because `BANISTER_TRIMP`'s own note
shipped a false "still not obtained" statement on `main`. The same reviewer
falsified two locators in the same session with the full suite green.

`MINETTI_2002`'s locator is load-bearing rather than decorative: its note
sources **both** published polynomials to that exact `Fig. 1 caption
(p. 1041)`. If the figure number or page drifts, the note's own attribution
points somewhere that does not contain what it claims — and nothing reds.

The residual is also **undeclared**, which is the part that makes it a
rejection-grade gap rather than an accepted limitation: nothing in the module
or the test file says these five are unpinned, so a session reading the test
module sees six citations, a backstop mechanism, and concludes the locators
are covered.

## Evidence

Both run by the reviewer against the committed state at `2098 passed`:

```
MINETTI_2002.locator:
  "Fig. 1 caption (p. 1041)" -> "Fig. 7 caption (p. 9999)"  (volume also changed)
  uv run pytest  ->  2098 passed          # SURVIVOR

COGGAN_TSS.locator:
  "revised 25 March 2003 edition" -> "revised 25 March 2013 edition"
  uv run pytest  ->  2098 passed          # SURVIVOR
```

For contrast, the one pinned locator now discriminates. The reviewer's
falsification of `BANISTER_TRIMP.locator` (`p. 408`→`p. 508`, `Eq. 2`→`Eq. 9`,
`p. 1172`→`p. 1999`, and `no multiplicative coefficient printed there`→`a
multiplicative coefficient printed there`) reds
`test_banister_is_now_primary_text_and_blocked_citations_is_empty` and
`test_banister_trimp_locator_mutation_evidence`. A length-preserving polarity
flip (`no`→`a `) also reds — the pin is a direct `==`, stricter than the
whitespace-normalized note pins.

## How to pick it up

1. Read `tests/load/channels/test_sources.py` — `BACKSTOP_BANISTER_TRIMP_LOCATOR`
   and its assertion are the pattern to copy. Note the note pins normalize
   whitespace and the locator pin does not; keep that distinction deliberate.
2. Add the five remaining constants. Each must be a **literal**, never derived
   from the module at import time, or the pin is self-satisfying.
3. Verify each with a mutation that changes only the locator — page, figure,
   edition or volume — and confirm sole failure.
4. If any locator is genuinely not worth pinning, say so in the test module
   with the mutation run that proves it unpinned. An honestly-declared
   residual is acceptable; an undeclared one is what this item is about.

## Open questions

Whether `Citation` should make this structural rather than per-field — a
single backstop over the whole frozen record (every field, not just `note` and
`locator`) would close this class permanently instead of one field at a time.
Worth weighing before adding five more constants.

## Resolution

**Status: done. Closed 2026-07-30**, merged to `main` at `63f9caf`
(`chore/citation-locator-backstops`, 3 commits), validated after rebase:
2297 passed, ruff + format + mypy clean.

All six `Citation.locator` fields now carry hand-retyped whole-value backstops
in `tests/load/channels/test_sources.py`. `src/fitdocs/load/channels/sources.py`
is **byte-identical** to its pre-change state — this was tests-only.

### Verified on `main` at close time

```
citations: 6  backstops: 6
keys equal: True
all match : True
```

### Discrimination

The reviewer ran 20 independent mutations. Every locator reds, each reddening
exactly three tests (tight sole-failure), including the two the item recorded as
survivors:

| mutation | before | after |
|---|---|---|
| `MINETTI_2002` `Fig. 1 (p. 1041)` → `Fig. 7 (p. 9999)` | 2098 passed | 3 failed |
| `COGGAN_TSS` `2003` → `2004` edition | 2098 passed | 3 failed |
| `MINETTI_2002` whitespace-only double space | — | 3 failed |
| `CITATIONS` → `()` | — | reds with "the walk is looking at the wrong registry" |
| add a 7th citation with no backstop | — | 2 failed |

The whitespace-only mutation mechanically confirms the pins are unnormalized
`==`, deliberately stricter than the note pins (which normalize whitespace).
The two are kept distinct on purpose.

### Completeness, not just per-field

`_LOCATOR_BACKSTOPS` is keyed by citation key rather than position, and
`test_every_citation_locator_is_pinned_by_a_backstop` asserts `len(CITATIONS) > 0`
before checking set-equality in **both** directions — so a seventh citation with
no backstop reds, and an orphan backstop reds. The reviewer verified all six loop
iterations discriminate independently by remapping each key in turn.

### One correction to this item's own premise

The item describes the five as "guarded only by `assert ... is not None`". That
vacuous assertion only ever existed for `BANISTER_TRIMP`; the other five had **no
locator coverage at all**. Same conclusion, slightly worse starting position.

### Residual, declared not silent

`Citation.authors`, `.year` and `.work` remain falsifiable with the suite green
(`MINETTI_2002.year 2002→2003` leaves 2297 passing). This is declared explicitly
in the test module rather than left implicit, and tracked at
`.kiro/queue/2026-07-30-citation-authors-year-work-unpinned.md`, which also
carries the deferred design question: whether `Citation` wants **one whole-record
backstop** instead of a third per-field dict. This is the second per-field round;
do not add a fourth mechanism without settling it.
