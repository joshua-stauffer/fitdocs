---
id: 2026-11-05-neutral-scan-leftovers-after-the-move
title: Leftovers in the neutral scan after its move
status: open
importance: low
importance_why: A dead table entry and a false docstring in a guard; the guard still works.
effort: S
kind: chore
area: connectors, tests/connectors/test_neutral_scan.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: Remove the dead intervals exemption and correct the zero-iteration docstring in test_neutral_scan.py, then refresh pointers to the scan's old home"
context:
  - tests/connectors/test_neutral_scan.py
  - .kiro/queue/2026-11-01-connectors-neutral-scan-loopback-literals.md
  - .kiro/queue/2026-10-02-connectors-boundary-and-neutrality-guard-gaps.md
  - .kiro/specs/connectors/design.md
blocked_by: []
---

## What
The `intervals.icu` exemption for `tests/connectors/test_intervals_docs.py` is dead, because `_unexercised_exemptions` checks per host and not per location. The conditional control's docstring says the real control is "currently zero-iteration", which is false. Two open queue items and `connectors/design.md` still place the scan in `test_docs.py`.

## Why it matters
Stale pointers cost the next reader, and a dead admission widens the guard slightly.

## Evidence
`tests/connectors/test_neutral_scan.py:47,529`. Task 1.1 reviewer: removing that exemption leaves the suite green. Old home named at `.kiro/specs/connectors/design.md:304,566,1580` and in the two queue items in `context`.

## How to pick it up
Delete the exemption, reword the docstring, and update the pointers. Consider making the exercised check per location.
