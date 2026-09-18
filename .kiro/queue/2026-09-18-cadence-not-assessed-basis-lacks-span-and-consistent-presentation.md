---
id: 2026-09-18-cadence-not-assessed-basis-lacks-span-and-consistent-presentation
title: The cadence-lock coverage-shortfall not-assessed basis skips the basis/span naming and the percentage presentation the reached-verdict basis uses
status: open
importance: medium
importance_why: Requirement 8.1 explicitly requires every reported coverage figure to name its basis and span; the reached-verdict path does this correctly and the not-assessed path (the majority case on 17 of 74 real files per research.md) does not, and renders the same quantity as a bare fraction instead of a percentage.
effort: S
kind: inconsistency
area: activity-qa-flags, src/fitdocs/load/qa/cadence.py, src/fitdocs/load/qa/flags.py
created: 2026-09-18
surfaced_by: /kiro-impl activity-qa-flags feature-level validation pass (kiro-validate-impl, Finding F-2)
pinned_at: d26b682
resume_command: "do: give cadence.py's gate-3 not_assessed_reason string the same 'time-weighted ... (measured over recorded time, not the document's own sample-count coverage table)' basis clause and percentage formatting that flags.py's _cadence_detail already uses for the reached-verdict path, then pin the corrected string with a test"
context:
  - src/fitdocs/load/qa/cadence.py
  - src/fitdocs/load/qa/flags.py
  - tests/load/qa/test_cadence.py
  - .kiro/specs/activity-qa-flags/requirements.md
---

## What

Two code paths report the same paired-coverage measurement with different
presentation and different basis-naming, and only one of them satisfies
Requirement 8.1/8.2.

The reached-verdict basis, built in `flags.py`'s `_cadence_detail`:

```
"time-weighted heart-rate/cadence paired coverage 61.0% (measured over
recorded time, not the document's own sample-count coverage table)"
```

The not-assessed reason, built inline in `cadence.py`'s gate 3
(`src/fitdocs/load/qa/cadence.py:300-313`), which `_cadence_detail` passes
through verbatim when the outcome is `NOT_ASSESSED`:

```
"heart-rate/cadence paired coverage 0.400 is below the configured minimum
0.500"
```

The second string has no "time-weighted" qualifier, no "measured over
recorded time" clause distinguishing it from the document's own sample-count
coverage table, and renders the fraction as `0.400` rather than `40.0%`.

## Why it matters

Requirement 8.1: "Where the fitdocs quality-flag layer reports a coverage or
proportion figure, it shall name the basis on which that figure was measured
and the span it covers." Requirement 8.2 requires the figure not be
presented as equivalent to the document's own per-channel coverage table.
The not-assessed path satisfies neither, and it is not a rare corner: the
research corpus measurement (`research.md`) records paired-coverage
shortfall (gate 3) as one of the two dominant not-assessed reasons for the
cadence check on real files.

Task 2.1 (which measures the coverage figure) claims 8.1/8.2 in its
`_Requirements:` line; task 2.2 (which wrote this exact string) claims
neither, so nobody currently owns fixing it.

## Evidence

Verified directly at `d26b682` (post-merge, pre-remediation-commit):

- `src/fitdocs/load/qa/flags.py:139-142` — the reached-path basis, with the
  "time-weighted" and "measured over recorded time" clauses
- `src/fitdocs/load/qa/cadence.py:308-313` — the not-assessed reason, bare
  fraction, no basis clause
- `tests/load/qa/test_cadence.py:174` asserts only `"coverage" in reason`
  on this path — the missing basis clause and the fraction-vs-percentage
  inconsistency are both unpinned

## How to pick it up

1. Read `src/fitdocs/load/qa/cadence.py`'s gate 3 (the `stream_coverage`
   shortfall branch) and `flags.py`'s `_cadence_detail`.
2. Rewrite the not-assessed reason string to carry the same basis clause and
   percentage formatting the reached path uses -- either duplicate the
   phrasing in `cadence.py`, or move the string-building into `flags.py`
   (where the reached-path basis already lives) so there is one place that
   knows how to render a paired-coverage figure.
3. Add or strengthen a test in `tests/load/qa/test_cadence.py` asserting the
   corrected string content, not just presence of the word "coverage".

Done looks like: the not-assessed reason names its basis and uses the same
percentage presentation as the reached-verdict basis, and a test pins the
exact wording.

## Open questions

None.
