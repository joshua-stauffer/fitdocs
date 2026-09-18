---
id: 2026-09-18-qa-docstrings-retain-task-number-narration
title: Production docstrings in load/qa still narrate the implementation plan by task number ("task 1.2 lands", "task 2.2 consumes", "this task") after 6fee8bd retired three such forward-references
status: open
importance: low
importance_why: Cosmetic; task numbers mean nothing to a reader of the shipped module and the same class of prose was already judged worth removing in 6fee8bd, which missed these.
effort: S
kind: docs
area: activity-qa-flags, src/fitdocs/load/qa/cadence.py, src/fitdocs/load/qa/types.py, src/fitdocs/load/qa/staleness.py
created: 2026-09-18
surfaced_by: /kiro-validate-impl activity-qa-flags (post-merge pass, 2026-09-18; design-alignment reviewer, confirmed by the controller)
pinned_at: e16acc3
resume_command: "do: rewrite the task-numbered sentences at src/fitdocs/load/qa/cadence.py:4-24, :49, :168, src/fitdocs/load/qa/types.py:110, :130 and src/fitdocs/load/qa/staleness.py:10 as descriptions of the shipped responsibility split (measurement in span_statistics, verdict in detect; provenance record in qa/sources.py; validation in the settings reader) with no task numbers; keep every docstring-pinning test in tests/load/qa/test_types.py, test_sources.py and test_cadence_spans.py green"
context:
  - src/fitdocs/load/qa/cadence.py
  - src/fitdocs/load/qa/types.py
  - src/fitdocs/load/qa/staleness.py
  - tests/load/qa/test_types.py
blocked_by: []
---

## What

`grep -n "task 1\.[0-9]\|task 2\.[0-9]\|task 3\.[0-9]\|this task" src/fitdocs/load/qa/*.py` at e16acc3:

```
cadence.py:4:   **Responsibility split between task 2.1 (this task) and task 2.2.** This
cadence.py:21:  modality/coverage/duration-summing logic only task 2.2 has the inputs for.
cadence.py:49:  configured width is never emitted, which is what lets task 2.2 treat
cadence.py:168: Note for task 2.2, which sums these spans' durations: ``len(result) *
staleness.py:10: **No pre-call ordering guard.** An earlier revision of this task checked
types.py:110:   which task 1.2 lands in ``qa/sources.py``. Neither published nor measured: no
types.py:130:   reader's job (task 1.3), not this dataclass's (Req 6.4).
```

Commit 6fee8bd ("fix three stale forward-references left after tasks
landed") already retired this class in `qa/__init__.py` and `qa/types.py`
but left these seven.

## Why it matters

A reader of the installed package has no `tasks.md`; "task 2.2" is
noise and "this task" is wrong (the module is not a task). The substantive
content of each sentence — which function owns which decision, where the
provenance record lives — is worth keeping in plain terms.

## Evidence

The grep above; `git show 6fee8bd --stat` for the precedent.

## How to pick it up

1. Run the grep; rewrite each hit in place, preserving the technical claim
   (e.g. cadence.py:168's `len(result) * window_s` warning is important;
   keep it, drop the addressee).
2. `uv run pytest tests/load/qa -q` — several tests pin docstring
   substrings (`test_types.py::_docstring_for`, `test_sources.py`,
   `test_cadence_spans.py`); adjust only if a pinned substring was itself a
   task number.
3. Done means the grep returns nothing and the qa suite is green.
