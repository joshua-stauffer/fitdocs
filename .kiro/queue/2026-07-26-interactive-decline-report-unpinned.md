---
id: 2026-07-26-interactive-decline-report-unpinned
title: Req 3.4's interactive-decline path is pinned at the prompt layer but never at the report
status: open
importance: low
importance_why: Both decline paths converge on MissingInputs inside the engine, so the reachable mutation surface is already covered.
effort: S
kind: gap
area: training-load, src/fitdocs/load/engine.py, tests/load/
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: 3121bb6
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-07-26-interactive-decline-report-unpinned.md] Pin the interactive-decline path through to the report bucket"
context:
  - .kiro/specs/training-load/requirements.md
  - src/fitdocs/load/prompts.py
  - tests/load/test_prompts.py
  - tests/load/test_cli_load.py
blocked_by: []
---

## What
Requirement 3.4 is one sentence spanning two layers: when a user declines to
supply a required field, the prompt flow returns it as still-missing, and the
command surface "shall skip load computation for the affected activities,
report the reason". Only task 1.2 claims it. The prompt half is pinned; the
report half is pinned only for the *non-interactive* case, which Req 3.5 owns.

## Why it matters
Low. Both the declined-interactively and the never-asked paths converge on
`MissingInputs` inside the engine, so the reachable mutation surface is
identical and already covered by Req 3.5's tests. What is unpinned is the
seam: that a decline actually propagates that far, rather than being swallowed
or turned into a failure.

## Evidence
`grep -rn 'ints=\[None\]' tests/` returns exactly one hit,
`tests/load/test_prompts.py:187`, at 3121bb6. No engine or CLI test drives a
user decline through `apply_load` to a report bucket.

## How to pick it up
Open `tests/load/test_prompts.py:185` for the decline fixture shape and
`tests/load/test_cli_load.py:416` for the non-interactive analogue that already
asserts the report half. Add one `apply_load` test with a scripted session
declining the field, asserting the document lands in `report.skipped` with the
missing-field reason and no profile file written. Done when deleting the
decline branch's propagation reddens it.
