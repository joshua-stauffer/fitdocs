---
id: 2026-09-18-flagprovenance-postcondition-binary-vs-shipped-three-way-classification
title: design.md's FlagProvenance Postcondition states a binary (citation or provisional) but the shipped, correct code implements a third "fitdocs' own choice with reasoning" category
status: open
importance: medium
importance_why: The design text is the only place this invariant is documented, and it currently contradicts the code it describes -- a later editor reading design.md and the code side by side would see an unexplained discrepancy, exactly the failure mode Requirement 6.10 exists to prevent.
effort: S
kind: inconsistency
area: activity-qa-flags, .kiro/specs/activity-qa-flags/design.md
created: 2026-09-18
surfaced_by: /kiro-impl activity-qa-flags task 1.2 review, re-confirmed at feature-level validation (Finding R1)
pinned_at: d26b682
resume_command: "do: restate design.md's FlagProvenance Postcondition (around design.md:713-718) as a three-way classification -- citation-backed, provisional, or fitdocs'-own-choice-with-reasoning -- matching Requirement 6.10's own text ('a value fitdocs chose, and where fitdocs chose it, the measurement OR REASONING that justifies it') and what tests/load/qa/test_sources.py already pins"
context:
  - .kiro/specs/activity-qa-flags/design.md
  - .kiro/specs/activity-qa-flags/requirements.md
  - src/fitdocs/load/qa/sources.py
  - tests/load/qa/test_sources.py
---

## What

`design.md`'s FlagProvenance Postcondition (around line 713-718) says every
default constant in `qa/types.py` "names either a citation key present in
`CITATIONS` or a key present in `PROVISIONAL_DEFAULTS`, and none names
both" -- a binary.

The shipped, reviewer-confirmed-correct implementation has a third category:
`DEFAULT_CADENCE_LOCK_WINDOW_S` and `DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE`
cite neither a `CITATIONS` entry nor a `PROVISIONAL_DEFAULTS` entry -- they
are "fitdocs' own choice," documented with reasoning in their own docstrings,
which Requirement 6.10's own text explicitly permits ("a value fitdocs
chose, and where fitdocs chose it, **the measurement or reasoning** that
justifies it").

## Why it matters

Two independent adversarial reviews (task 1.2's review and the feature-level
validation pass) read the design text and the code side by side and flagged
the same contradiction. The code is right -- `tests/load/qa/test_sources.py`
pins the third category and a mutation forcing those two constants into
`PROVISIONAL_DEFAULTS` reds three tests -- so this is a documentation
correction, not a re-implementation. Left as-is, the design doc keeps
reporting a false invariant every time someone reads it.

## Evidence

- `.kiro/specs/activity-qa-flags/design.md:713-718` (Postcondition text)
  vs `.kiro/specs/activity-qa-flags/requirements.md` Req 6.10 ("the
  measurement or reasoning")
- `src/fitdocs/load/qa/types.py` -- `DEFAULT_CADENCE_LOCK_WINDOW_S` and
  `DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE` docstrings, neither naming a
  citation nor a provisional entry
- `tests/load/qa/test_sources.py::test_fitdocs_own_choice_defaults_are_exempt_from_both`
  pins the third category directly

## How to pick it up

1. Read design.md's FlagProvenance Postcondition and `qa/sources.py`'s
   module docstring (which already documents the ruling informally).
2. Rewrite the Postcondition sentence to state the three-way classification
   explicitly, matching Req 6.10's "measurement or reasoning" wording.
3. Re-run `/kiro-spec-status activity-qa-flags` or a mechanical
   re-verification pass over design.md to confirm no other sentence in the
   same section still states the binary.

Done looks like: design.md's Postcondition and the shipped code agree, and
nothing else in design.md repeats the binary framing.

## Open questions

None.
