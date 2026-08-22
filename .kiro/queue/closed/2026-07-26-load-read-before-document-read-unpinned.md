---
id: 2026-07-26-load-read-before-document-read-unpinned
title: Req 14.6's "before any document is read" is pinned only as "before the loop"
status: done
importance: medium
importance_why: A plausible refactor (skip settings I/O when there are no documents) lands exactly in the unguarded gap.
effort: S
kind: gap
area: training-load, src/fitdocs/load/engine.py, tests/load/
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: 3121bb6
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-07-26-load-read-before-document-read-unpinned.md] Pin Req 14.6's before-any-document-is-read clause with read instrumentation"
context:
  - .kiro/specs/training-load/requirements.md
  - src/fitdocs/load/engine.py
  - tests/load/test_arbitration_e2e.py
  - tests/load/test_engine.py
blocked_by: []
---

## What
Requirement 14.6 requires a malformed `[load]` table to abort "before any document is read or written". Task 6.1's empty-`workouts/` fixture pins "before the per-document loop", which is weaker: `_discover_workout_docs` reads every candidate's frontmatter via `_read_frontmatter` before the loop begins.

## Why it matters
Moving `apply_load`'s settings resolution and `validate_configured` to sit after `_discover_workout_docs(data_root)` leaves the entire suite green while every document has already been read. The requirement's literal clause is unguarded. A future "skip the settings read when there are no documents" optimisation lands precisely there.

## Evidence
Reported and measured by the task 6.1 reviewer: with the validation block moved after `_discover_workout_docs`, `uv run pytest -q` returned 1831 passed at that time, including both `..._aborts_up_front_with_no_documents` analogues in `tests/load/test_engine.py`. Not re-measured at 3121bb6; the structural fact (`_discover_workout_docs` reads frontmatter, `engine.py:589-596`) is verified.

## How to pick it up
Read `src/fitdocs/load/engine.py:255-300` (the up-front block) and `:576-600` (discovery). Pinning this needs read-instrumentation unlike anything else in the suite -- e.g. spy `Path.read_text` or `_read_frontmatter` and assert zero calls before the settings error is raised. Done when the mutation above reddens a test.


## Resolution

**Done 2026-07-26** — `1bd4dad`, branch `chore/queue-top-ten`.

`tests/load/test_arbitration_e2e.py::test_malformed_load_table_aborts_before_any_document_is_read`
spies `_read_frontmatter` and asserts zero calls before the settings error is
raised -- the "indistinguishable outcome" anti-pattern answered by finding a
different observable rather than by declaring the clause unpinned.

It carries its own reachability control: a well-formed pass runs first and the
spy must observe reads, so the zero-count assertion cannot be satisfied by a spy
patched onto the wrong name. Verified by misdirecting the spy -- the control
fires with "the spy observed no reads even on a well-formed pass".

Under the ordering mutation the item names (validation moved after
`_discover_workout_docs`), the suite goes from 1868 green to exactly one
failure: this test. Sole failure.
