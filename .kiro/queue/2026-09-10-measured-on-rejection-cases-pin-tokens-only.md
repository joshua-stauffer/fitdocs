---
id: 2026-09-10-measured-on-rejection-cases-pin-tokens-only
title: The benchmark parser's measured_on rejection cases assert scope and quantity tokens only, never the entry index or the offending value, unlike the applies_from cases added beside them
status: open
importance: low
importance_why: Requirement 2.4's "naming the file and the offending entry" is pinned for applies_from (index and ISO dates asserted since 2026-09-10) but not for measured_on, so the two fields' messages can drift apart and a measured_on message that stops naming which entry failed ships green.
effort: S
kind: gap
area: athlete-benchmarks, src/fitdocs/benchmarks.py, tests/test_benchmarks.py
created: 2026-09-10
surfaced_by: /kiro-impl training-load (Amendment 4, task 7.1 review round 5)
pinned_at: 52c473e
resume_command: "do: extend the measured_on cases in tests/test_benchmarks.py REJECTION_CASES (missing_measured_on, non_date_measured_on, datetime_measured_on_rejected_even_though_it_subclasses_date) with the '[0]' entry index and, where the message carries it, the offending value; verify by mutation that dropping the index from the path or the value from the message reds them"
context:
  - tests/test_benchmarks.py
  - src/fitdocs/benchmarks.py
  - .kiro/specs/athlete-benchmarks/requirements.md
blocked_by: []
---

## What

`tests/test_benchmarks.py` `REJECTION_CASES` for `measured_on`
(`missing_measured_on`, `non_date_measured_on`,
`datetime_measured_on_rejected_even_though_it_subclasses_date`, ~lines
270-285) expect only `("run", "ftp_watts")`. The `applies_from` cases beside
them expect the field name, and the round-3/round-6 remediations added the
`[0]` index and the offending ISO value for the `applies_from` bound and type
cases. The 7.1 round-5 reviewer ran the analogous `measured_on` mutations
(`path=kind_path`, dropping the value from the message) and the suite stayed
green.

## Why it matters

Requirement 2.4 asks that a bad measurement date fail "naming the file and
the offending entry". With an array of entries under one quantity, "the
entry" is the index; a message that loses it sends the athlete hunting
through the array. The asymmetry between the two date fields is what makes it
easy to break one without noticing.

## Evidence

- `tests/test_benchmarks.py` ~L270-285 (measured_on cases) vs the
  `applies_from` cases that follow, and the `names_index_and_dates` tests
  added by 7.1's remediation.
- 7.1 review round 5, finding 4 and FOLLOW_UPS item 2 (Opus reviewer,
  2026-09-10): "`path=kind_path` for the `applies_from` call only … and
  dropping the ISO dates … both leave the suite green; the existing
  `measured_on` rejection cases share this weakness".

## How to pick it up

1. Read `_validate_measured_on` (or the equivalent) in
   `src/fitdocs/benchmarks.py` to see exactly what the message carries.
2. Extend the three cases' expected substrings; run the two mutations.
3. Done: both mutations red at least one `measured_on` case.
