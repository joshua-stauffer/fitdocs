---
id: 2026-08-25-default-min-duration-lacks-citation-and-status
title: DEFAULT_MIN_DURATION_S carries no citation and no verification status, and it is the fitdocs-chosen constant Req 8.2 asserts this feature does not introduce
status: open
importance: medium
importance_why: A live Req 8.3 violation in merged code, and it falsifies Req 8.2's standing claim; the vocabulary to record it honestly (FITDOCS_MEASURED) already exists and is unused.
effort: S
kind: inconsistency
area: load-channels, src/fitdocs/load/channels/types.py, src/fitdocs/load/channels/sources.py
created: 2026-08-25
surfaced_by: /kiro-impl load-channels (task 4.2 provenance sweep; verified independently by the parent session)
pinned_at: 4390887
resume_command: "/kiro-impl load-channels [queue: .kiro/queue/2026-08-25-default-min-duration-lacks-citation-and-status.md] Record DEFAULT_MIN_DURATION_S through the citation vocabulary as FITDOCS_MEASURED, and correct Req 8.2's claim that this feature introduces no such constant"
context:
  - src/fitdocs/load/channels/types.py
  - src/fitdocs/load/channels/sources.py
  - .kiro/specs/load-channels/requirements.md
  - tests/load/channels/test_purity.py
blocked_by: []
---

## What

`src/fitdocs/load/channels/types.py:164` defines

```python
DEFAULT_MIN_DURATION_S: Final[int] = 60
```

with a docstring that is honest about its provenance and names no citation:

> The documented default minimum activity duration (Req 3.3). This one is
> fitdocs' own, not a published figure: 60 s is twice the 30 s rolling window
> the shipped normalized-power algorithm needs, the longest window any
> channel's inputs require.

Two things follow.

**1. It violates Req 8.3 as written.** That criterion says the layer "shall not
introduce a numeric constant without a citation **and a stated verification
status**". This constant has neither — not at its point of definition, not in
`sources.py`'s `CITATIONS`.

**2. It falsifies a standing claim in Req 8.2.** That criterion defines exactly
three verification statuses, the third being *"chosen by fitdocs and justified
by a recorded measurement rather than by a published source"*, and then states:

> This feature introduces no constant of its own carrying the third status; the
> status exists so that a sibling feature's measured defaults can be recorded
> honestly through the same vocabulary rather than by extending it later.

`DEFAULT_MIN_DURATION_S` **is** a constant of this feature's own, chosen by
fitdocs, justified by a recorded derivation rather than a published source. It
is the third status's own description. The claim that no such constant exists
is not true — the constant exists and simply is not recorded through the
vocabulary.

`sources.py:20-28` carries the matching assertion that `FITDOCS_MEASURED` is
"carried in full even though no citation in *this* package carries it".

## Why it matters

The fix is cheap and the vocabulary already exists — that is precisely what
makes the gap worth closing rather than tolerating. `FITDOCS_MEASURED` was
deliberately defined for this shape of value, by this feature, and then not used
for the one value in this feature that fits it.

Leaving it costs three ways:

- Task 4.2's provenance guard (`tests/load/channels/test_purity.py`) has to ship
  a named allowlist exception for `types.py` rather than enforcing the rule
  cleanly. An allowlist is a place future violations can hide.
- Req 8.2 and `sources.py`'s module docstring both assert something untrue, and
  this repo's recorded lesson is that a false claim in prose is worse than no
  claim — it tells the next reader the state is other than it is.
- `activity-qa-flags` is the declared consumer of `FITDOCS_MEASURED`. It will
  record its measured defaults through a status this package says it never
  uses, while this package quietly holds an unrecorded instance of it.

Note this is a *recording* gap, not a wrong number. The 60 s value has a stated,
checkable derivation (twice the 30 s normalized-power window). Nothing computed
is affected.

## Evidence

Measured at `4390887`.

Module-level numeric constants in `types.py`, extracted by AST (both `Assign`
and `AnnAssign`):

```
DEFAULT_MIN_STREAM_COVERAGE = 0.8    (types.py:155)
DEFAULT_MIN_DURATION_S      = 60     (types.py:164)
```

`DEFAULT_MIN_STREAM_COVERAGE` **does** cite — its attribute docstring
(`types.py:156-162`) names `TRAININGPEAKS_COVERAGE_GATE` in `sources.py` and is
explicit that applying a bike/power figure across all three channels is fitdocs'
own scope decision, recorded on the citation itself. `DEFAULT_MIN_DURATION_S`
names nothing.

Requirement text: `.kiro/specs/load-channels/requirements.md`, Requirement 8,
criteria 1 ("at the point of definition"), 2 (the three statuses and the
"introduces no constant" claim) and 3 (the prohibition).

The enum member and its "no citation here carries it" claim:
`src/fitdocs/load/channels/sources.py:20-28`.

Surfaced by task 4.2's provenance sweep, which reports `uncited == {'types'}`
when its exception set is emptied. The parent session re-derived the constants
and read both docstrings before filing.

*A caution for whoever picks this up:* an AST walk that matches only
`ast.Assign` finds **zero** constants in this file, because both are annotated
(`Final[int] = 60` is an `ast.AnnAssign`). The parent session's first scan made
exactly that mistake and reported a clean sweep having inspected nothing — the
repo's *vacuous walk* pattern. Handle `AnnAssign`.

## How to pick it up

1. Read `types.py:155-169` (both constants and their docstrings) and Requirement
   8's criteria 1-3.
2. Decide the recording. The natural form is a `Citation`-shaped record in
   `sources.py` with `FITDOCS_MEASURED`, naming the derivation (twice the 30 s
   rolling window the shipped normalized-power algorithm requires) rather than
   an author and year, referenced from the constant's own docstring the way
   `DEFAULT_MIN_STREAM_COVERAGE` references `TRAININGPEAKS_COVERAGE_GATE`.
3. Correct Req 8.2's "This feature introduces no constant of its own carrying
   the third status" and the matching sentence at `sources.py:20-28`. A
   requirements edit needs whatever re-approval the spec phase requires.
4. Once recorded, remove `types` from `test_purity.py`'s
   `_KNOWN_UNCITED_MODULES` and confirm the guard still passes — and confirm it
   still *reds* for a genuinely uncited constant by adding one temporarily.

**Done** looks like: no module-level numeric constant in the package lacks a
citation and a stated status, the purity guard needs no allowlist exception, and
no requirement or docstring claims the third status is unused when it is used.

## Open questions

- Does `DEFAULT_MIN_STREAM_COVERAGE` also need to change? It satisfies Req 8.1
  ("at the point of definition") but fails task 4.2's guard, which looks in the
  *module* docstring. That is a guard-stricter-than-requirement mismatch and may
  be better fixed in the guard than in the constant — worth settling in the same
  sitting, since both constants live four lines apart.
