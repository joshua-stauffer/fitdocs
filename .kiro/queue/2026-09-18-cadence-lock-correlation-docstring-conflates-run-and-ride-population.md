---
id: 2026-09-18-cadence-lock-correlation-docstring-conflates-run-and-ride-population
title: The DEFAULT_CADENCE_LOCK_MIN_CORRELATION docstring (and design.md) attribute the corpus's 0.605 max correlation to the wrong population -- it's the Ride max, not the Run max the surrounding sentence describes
status: open
importance: medium
importance_why: Requirement 6.10 requires a measured default's docstring to accurately name the measurement that justifies it; the current text misstates which activity type produced the cited figure, in the one constant this spec's own provenance requirement exists to police.
effort: S
kind: inconsistency
area: activity-qa-flags, src/fitdocs/load/qa/types.py, .kiro/specs/activity-qa-flags/design.md
created: 2026-09-18
surfaced_by: /kiro-impl activity-qa-flags feature-level validation pass
pinned_at: d26b682
resume_command: "do: correct DEFAULT_CADENCE_LOCK_MIN_CORRELATION's docstring in qa/types.py and design.md:725 to match qa/sources.py's already-correct phrasing -- Run: median 0.157, max 0.552 (n=40); Ride max 0.605 -- rather than the current sentence which reads as if 0.605 is the Run population's own peak"
context:
  - src/fitdocs/load/qa/types.py
  - src/fitdocs/load/qa/sources.py
  - .kiro/specs/activity-qa-flags/design.md
  - .kiro/specs/activity-qa-flags/research.md
---

## What

Three places in this spec cite the corpus's whole-activity Pearson
correlation statistics. Two of them conflate which activity type produced
the 0.605 maximum; one states it correctly.

`src/fitdocs/load/qa/types.py:85` (the `DEFAULT_CADENCE_LOCK_MIN_CORRELATION`
docstring) and `.kiro/specs/activity-qa-flags/design.md:725` both read:

> "...real activity corpus peaks at 0.605 across 40 assessable runs (median
> 0.157)"

`src/fitdocs/load/qa/sources.py:152` states the same underlying data
correctly:

> "...median 0.157, max 0.552 (n=40 assessable runs); ride max 0.605."

`research.md:140`'s own table confirms `sources.py`'s version: "Run: min
−0.225, median 0.157, max 0.552 (n=40); Ride max 0.605".

The `types.py`/`design.md` phrasing reads as though 0.605 is itself a
statistic *of the 40 assessable runs*, when it is actually the separate
Ride population's maximum (10 rides in the corpus, a different modality).

## Why it matters

Requirement 6.10 requires a measured default's docstring to name the
measurement that justifies it accurately. The shipped 0.90 threshold is
correct and well-headroomed either way this is read (0.605 < 0.90 either as
Run or Ride max), so no behavior is wrong -- but the constant this
requirement exists to police is exactly the one whose provenance sentence
currently misattributes its own cited figure.

## Evidence

Verified at `d26b682`:
```
$ grep -n "0.605\|0.552" src/fitdocs/load/qa/types.py src/fitdocs/load/qa/sources.py .kiro/specs/activity-qa-flags/design.md .kiro/specs/activity-qa-flags/research.md
src/fitdocs/load/qa/types.py:85:real activity corpus peaks at 0.605 across 40 assessable runs (median
src/fitdocs/load/qa/sources.py:152:    "median 0.157, max 0.552 (n=40 assessable runs); ride max 0.605. Median "
.kiro/specs/activity-qa-flags/design.md:725:  real corpus peaks at 0.605 across 40 assessable runs (median 0.157);
.kiro/specs/activity-qa-flags/research.md:140:  | Whole-activity Pearson r, HR vs 2×cadence | Run: min −0.225, median 0.157, max 0.552 (n=40); Ride max 0.605; ... |
```

## How to pick it up

1. Read `research.md:140`'s table for the authoritative figures.
2. Rewrite `types.py:85`'s docstring and `design.md:725` to match
   `sources.py:152`'s already-correct phrasing: Run max 0.552 (n=40,
   median 0.157), Ride max 0.605.
3. Re-run `uv run pytest tests/load/qa/ -q` to confirm no test asserts the
   old (wrong) sentence verbatim (unlikely, but check).

Done looks like: all three documents agree on which population produced
which figure.

## Open questions

None.
