---
id: 2026-07-25-devfield-declared-scale-ignored
title: A developer field's declared scale/offset is silently dropped by the SDK
status: done
importance: medium
importance_why: Latent today (no corpus file declares one), but it would produce a silently wrong number for every consumer, and Req 14.2's wording currently endorses it.
effort: S
kind: gap
area: fit-ingest, src/fitdocs/ingest/summary.py
created: 2026-07-25
surfaced_by: /kiro-validate-design on the Avg METs scale defect
pinned_at: 2a01dfd
resume_command: "/kiro-spec-requirements fit-ingest [queue: .kiro/queue/2026-07-25-devfield-declared-scale-ignored.md] Stop silently dropping a developer field's declared scale/offset, and correct Req 14.2's wording that endorses it"
context:
  - src/fitdocs/ingest/summary.py
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/design.md
blocked_by: []
---

## What

The FIT `field_description` message can declare `scale` and `offset` for a
developer field. `garmin-fit-sdk` parses both into its field profile but **never
applies them to developer fields** — only to native profile fields. So
`extract_developer_fields` returns a raw integer even when the file explicitly
declares how to scale it, and fitdocs has no way to notice.

This is a different problem from the `AVG METs` defect just fixed. There, the
writer declared *no* scale and the hundredths encoding was a convention we had
to infer. Here the file *tells* us the scale and we drop it.

It also exposes an ambiguity in `fit-ingest` Req 14.2, which mandates passing
values through "without interpretation, derivation, or renaming". Applying a
scale the file itself declares is arguably decoding, not interpretation — the
requirement should say which it means.

## Why it matters

Latent, not active: all six developer-field descriptors in the current corpus
declare `scale=None`. But if any writer ever declares one, every consumer of
`Activity.developer_fields` silently receives a wrong-by-a-constant-factor
number with no error and no signal. The cost of clarifying Req 14.2's wording
grows as more features read developer fields (`training-load` and
`athlete-benchmarks` both plan to).

## Evidence

In `.venv/lib/python3.11/site-packages/garmin_fit_sdk/decoder.py`:

- `:317` — the developer-field decode path stores the raw value directly:
  `developer_fields[field_profile['key']] = field_value`, with no scale applied.
- `:443-444` — `__apply_scale_and_offset` is called only from `__apply_profile`,
  which handles native fields; developer fields never reach it.
- `:670-671` — the field profile *does* carry the declared values
  (`'scale': message['scale']['raw_field_value'] if 'scale' in message else None`),
  so the information is parsed and then unused for this path.

Corpus check over 74 files — every descriptor declares no scale, which is why
this has never fired:

```
field_name                        rec  scale/offset/units/basetype
AVG METs                           64  [(None, None, None, 132)]
SESSION ACTIVITY TYPE              70  [(None, None, None, 143)]
SESSION INDOOR                     70  [(None, None, None, 2)]
SESSION UUID                       70  [(None, None, None, 2)]
SESSION WEATHER HUMIDITY           16  [(None, None, None, 132)]
WORKOUT RPE ESTIMATED              14  [(None, None, None, 2)]
```

## How to pick it up

1. Read `extract_developer_fields` and `_developer_value` in
   `src/fitdocs/ingest/summary.py:114-165` — the docstring already documents the
   SDK's positional `key` convention and is the right place to document scale.
2. Settle the contract question first, in `fit-ingest` Req 14.2: does "verbatim"
   mean the bytes as decoded, or the value as the file declares it? The second
   reading is the defensible one — a declared scale is part of the encoding, not
   an interpretation of it.
3. If Req 14.2 is clarified to apply declared scale/offset, implement it in
   `_developer_value` (the description is already in hand at the call site) and
   add a fixture that declares a non-null scale — no current fixture does, which
   is why no test covers this. Done means a developer field declaring
   `scale=10` arrives divided by 10, and one declaring none is unchanged.

## Open questions

- Should a declared `units` string also be surfaced? It is parsed and dropped by
  the same path, and it would let the render layer stop hardcoding unit suffixes.
  Still open: `Activity.developer_fields_declared_scale` (below) surfaces
  DECLAREDNESS only, by deliberate maintainer ruling — not `units`,
  `components`, `bits`, or `accumulate`.

## Proposed resolution (2026-07-27, branch `impl/devfield-declared-scale`)

**Status is intentionally still `open` — this is a proposal on an unmerged
branch, not a closure.** Commit `1b52bc8 (rebased from the pre-review SHA f73fa99)` on that branch implements the
decode step this item describes (`extract_developer_fields_with_declared_scale`
in `src/fitdocs/ingest/summary.py`, Req 14.2 as amended in
`.kiro/specs/fit-ingest/requirements.md`), and a follow-up commit on the same
branch fixes a critical regression the first commit introduced: the render
layer (`src/fitdocs/render/sections.py`'s `_SUPPLEMENTALS` fallback) was
unconditionally multiplying by its own hundredths-guess factor, which would
have silently turned an already-correctly-decoded declared-scale value 100x
wrong on the rendered page. `Activity.developer_fields_declared_scale`
(a `frozenset[str]`) now carries the fact the render layer needs to avoid
that double-scaling — maintainer-ruled to surface declaredness only, not the
full field description. `scale=0` is maintainer-ruled to OMIT the field
rather than emit a raw value. Both rulings and the render fix are recorded in
`.kiro/specs/fit-ingest/requirements.md`'s Amendment 2 revision and
`design.md`. This item should be closed only once that branch merges to
`main` — do not close it from this note alone.

## Resolution (2026-07-27) — done

`impl/devfield-declared-scale` merged to `main` (`--ff-only`), so the condition
the proposal note above set for closing ("only once that branch merges") is met.
Verified on `main` at `acf5778`, not on assertion:

- `f1786d2 fix(fit-ingest): decode a developer field's declared scale/offset (Req 14.2)`
  — `extract_developer_fields_with_declared_scale` in
  `src/fitdocs/ingest/summary.py:146` applies the FIT formula
  `value / scale - offset`, defaulting an undeclared term to identity, and
  returns the `frozenset` of names whose description declared one.
- `4880a6c fix(fit-ingest): stop double-scaling a declared-scale developer field in render`
  — `src/fitdocs/render/sections.py:257` applies its hundredths fallback only
  for keys ABSENT from `activity.developer_fields_declared_scale`, closing the
  100x regression the first commit introduced.
- `Activity.developer_fields_declared_scale` exists at `src/fitdocs/model.py:231`
  and is populated in `src/fitdocs/ingest/__init__.py:85`.
- The contract question this item raised is settled in the spec, not left
  implicit: `.kiro/specs/fit-ingest/requirements.md:128` (Amendment 2) and
  Req 14.2 at `:412` draw the line — a file-DECLARED scale/offset is decoding
  and is now required; an UNDECLARED convention remains forbidden. A declared
  `scale=0` OMITS the field (maintainer ruling, never a raw fallback).
- Tests: 22 pass under `-k "declared_scale or developer_field"`; full gate on
  `main` is green — 2064 passed, `ruff check`, `ruff format --check`, and
  `mypy --strict src` all clean.

Left open deliberately: the "should a declared `units` string also be surfaced?"
open question. It was maintainer-ruled OUT of this amendment (declaredness only,
not `units`/`components`/`bits`/`accumulate`), so it is a scoped-out decision
rather than unfinished work on this item.
