---
id: 2026-07-29-moving-threshold-justification-over-narrows
title: MOVING_THRESHOLD_CHOICE's justification describes a rule the code does not implement, and a whole-value backstop pins the false text character-for-character
status: open
importance: high
importance_why: A shipped FitdocsChoice record states, as its Req 15.8 justification, a rule the production code contradicts — and the backstop guarding it makes the falsehood harder to notice, not easier.
effort: S
kind: bug
area: fit-ingest, src/fitdocs/metrics/sources.py, tests/metrics/test_sources.py
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.1, review rounds 1-2)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-29-moving-threshold-justification-over-narrows.md] Correct MOVING_THRESHOLD_CHOICE's justification so the distance fallback is not described as speed-less-only, and move its backstop with it"
context:
  - src/fitdocs/metrics/sources.py
  - tests/metrics/test_sources.py
  - src/fitdocs/metrics/aggregates.py
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

`MOVING_THRESHOLD_CHOICE.justification` in `src/fitdocs/metrics/sources.py`
describes the moving-time rule as:

> treating a sample above it (or a cumulative-distance increase across the
> pair, **for a speed-less channel**) as 'moving'

The parenthetical restricts the cumulative-distance fallback to a channel with
no speed data. The code applies that fallback whenever the speed test fails —
including when a speed sample is *present* but at or below the threshold.

The identical wording was found and fixed inside `aggregates.py`'s own
docstring during task 10.1. This copy, in the committed record, was ruled out
of that task's boundary and left standing.

## Why it matters

This is not a comment. It is the `justification` field of a `FitdocsChoice`
record, which is the artifact Requirement 15.8 requires for a value no
published work defines — the record exists precisely so the reasoning behind
the number is inspectable. A justification that misdescribes the rule the
number participates in is the failure that requirement is written to prevent.

It is made worse by its own guard: the text is pinned verbatim by
`BACKSTOP_MOVING_THRESHOLD_JUSTIFICATION` (`tests/metrics/test_sources.py:795`,
asserted at `:983`). The backstop works exactly as designed — it stops drift —
but it means the false sentence is now protected character-for-character, and
any future session that notices the discrepancy and corrects the record will
be met with a red test that looks like *they* broke something. This is the
concrete instance of the lesson recorded in the agent log after task 9.4: a
whole-value backstop pins text, not truth.

## Evidence

Record text: `src/fitdocs/metrics/sources.py:261-262`.

Counter-example, run at `4449d3e`:

```
$ uv run python -c "... _derive_moving_time_s ..."
sub-threshold speed 0.2 + rising distance -> 1.0
sub-threshold speed 0.2 + flat distance   -> 0.0
```

A speed of 0.2 m/s is *present* and below the 0.5 m/s threshold, so by the
record's wording the distance branch should not apply — but the pair is
counted as moving when distance rises, and not counted when it does not. The
branch is reached by the failure of the speed test, not by the absence of
speed data. The production code is correct; the record's description of it is
not.

The already-corrected sibling wording is at `src/fitdocs/metrics/aggregates.py`
(task 10.1, commit `4449d3e` on `impl/fit-ingest`), where the same sentence was
rewritten after review rejected it.

## How to pick it up

1. Read `src/fitdocs/metrics/aggregates.py`'s `_MOVING_SPEED_THRESHOLD_MPS`
   docstring first — it is the wording that already survived review for this
   exact rule, and reusing its shape avoids re-deriving the phrasing.
2. Fix `sources.py:261-262`. The load-bearing correction is that the distance
   fallback applies whenever the speed test does not judge the pair moving,
   which includes a present sub-threshold speed — not only a speed-less
   channel.
3. Move `BACKSTOP_MOVING_THRESHOLD_JUSTIFICATION` in the same change
   (`tests/metrics/test_sources.py:795`). The backstop is correct machinery and
   should be kept, not weakened; it just has to carry the corrected text.
4. Done means: the record describes the rule the code implements, the backstop
   pins the corrected text, and `uv run pytest` is green.

This is a records-prose change, so the discipline from tasks 9.1-9.4 applies:
verdict the claim against evidence you ran, not against the previous wording.

## Open questions

None. The maintainer has already ruled on the equivalent wording in
`aggregates.py` by approving task 10.1; this is the same correction in the
record that task's boundary excluded.
