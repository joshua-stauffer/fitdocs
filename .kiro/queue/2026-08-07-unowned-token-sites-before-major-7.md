---
id: 2026-08-07-unowned-token-sites-before-major-7
title: Three token sites under tests/ have no owning task and a one-shot deadline
status: open
importance: medium
importance_why: Req 11.1 binds every tracked file, no task in Majors 4 or 5 names these modules, and after the history rewrite the omission is permanent.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge, .kiro/specs/encumbered-content-purge/tasks.md
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (tasks 3.11, 4.3 reviews)
pinned_at: 7d49c84
resume_command: "do: Decide an owner for the token-literal detections in tests/purge/test_tree_removal.py and the bare token in tests/test_forbidden_strings_source.py's docstring, then land the change before Major 7 runs."
context:
  - tests/purge/test_tree_removal.py
  - tests/test_forbidden_strings_source.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

Three sites under `tests/` still carry identifying tokens as Python literals,
and no task in the plan names the modules they live in.

Two are token-literal absence assertions and a copyright-notice comment in
`tests/purge/test_tree_removal.py`. Task 4.1 owns the packaging guard, 4.2 the
documentation guard, 4.4 the CLI and contributor-doc detections -- none owns
this module, because it post-dates the design's modified-files table. The third
is a bare token inside a quoted basename in
`tests/test_forbidden_strings_source.py`'s docstring, which the sweep inventory
has no row for.

## Why it matters

Req 11.1 binds every tracked file's content, and Req 11.7 requires a
token-literal guard to be re-based or retired rather than kept. These are the
last known token sites the plan does not reach. The history rewrite is one-shot:
after it runs, a site nobody redacted is a site nobody can redact.

## Evidence

Task 3.11's reviewer enumerated the token sites remaining under `tests/` after
that task and found these three outside every task's boundary, cross-checking
against the module lists in tasks 4.1 through 4.4. Task 4.3's reviewer
re-measured the tie probe on the third site and found a token hit with no
tied path hit on that line, which is the discriminating check this repo uses.

## How to pick it up

Read the three sites. Decide whether the absence assertions can be retired now
that task 4.3's standing guard covers the same property from outside-supplied
data -- that is the same reasoning task 4.4 used for its own two retirements.
The docstring basename is a plain redaction. Whichever way, the change must
land before Major 7. Done when the fixed-string tie probe over `git ls-files
tests` returns only sites a task's text names.

## Open questions

Whether retiring the absence assertions loses coverage the standing guard does
not replace. Task 4.4 answered the same question by planting a token and
observing the standing guard red before deleting anything; the same experiment
answers it here.
