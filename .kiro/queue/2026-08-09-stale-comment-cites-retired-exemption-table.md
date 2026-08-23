---
id: 2026-08-09-stale-comment-cites-retired-exemption-table
title: A historical comment in test_contributing_calculators_doc.py names the exemption table and test task 6.3 retired
status: open
importance: low
importance_why: Purely documentation staleness -- the comment describes a past event correctly in substance, but two of the identifiers it names (`_CONTENT_EXEMPT_VALUES`, `test_reviewed_exemption_rejects_a_different_value_in_the_same_file`) no longer exist in the codebase, so a reader following the reference finds nothing.
effort: S
kind: docs
area: tests/test_contributing_calculators_doc.py, tests/test_forbidden_strings.py
created: 2026-08-09
surfaced_by: encumbered-content-purge task 6.3 (retiring `_CONTENT_EXEMPT_VALUES` and its four pinning tests)
pinned_at: c3d2201
resume_command: "do: reword the historical comment block in tests/test_contributing_calculators_doc.py (around the paragraph beginning \"A second, narrower gap existed briefly during this repair\") so it describes the same task-4.4 event without naming `_CONTENT_EXEMPT_VALUES` or `test_reviewed_exemption_rejects_a_different_value_in_the_same_file` by identifier -- both were removed by encumbered-content-purge task 6.3, which retired the reviewed-exemption mechanism entirely once the tracked tree carried zero forbidden values [queue: .kiro/queue/2026-08-09-stale-comment-cites-retired-exemption-table.md]"
context:
  - tests/test_contributing_calculators_doc.py
  - tests/test_forbidden_strings.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`tests/test_contributing_calculators_doc.py` carries a comment block (around
line 106-124) recording a task-4.4 repair: a stale
`_CONTENT_EXEMPT_VALUES` table entry that briefly left a real detection hole.
The comment names two identifiers by their exact text --
`_CONTENT_EXEMPT_VALUES` and
`test_reviewed_exemption_rejects_a_different_value_in_the_same_file` -- both
of which `encumbered-content-purge` task 6.3 removed outright: the whole
reviewed-exemption mechanism was retired once the tracked tree was driven to
zero forbidden-value occurrences (task 6.3's own observable), so an
exemption table has nothing left to exempt.

## Why it matters

The comment's substance (what happened, when, how it was measured) is still
accurate as history. But a reader who greps for either identifier today, or
who opens `tests/test_forbidden_strings.py` expecting to find the named
test, finds nothing -- the reference has gone stale. Low severity (no
behavioural effect, no forbidden value involved), but it is exactly the kind
of small dangling pointer that accumulates unless someone reconciles it.

## Evidence

```
$ grep -rn "_CONTENT_EXEMPT_VALUES" --include="*.py" .
tests/test_contributing_calculators_doc.py:114:# `_CONTENT_EXEMPT_VALUES` table had kept listing this module for the
```

`_CONTENT_EXEMPT_VALUES` and
`test_reviewed_exemption_rejects_a_different_value_in_the_same_file` no
longer exist anywhere in `tests/test_forbidden_strings.py` as of task 6.3
(`f79622a`'s working tree, pre-commit).

## How to pick it up

1. Read `tests/test_contributing_calculators_doc.py` lines ~96-125 for the
   full comment block and what it records.
2. Reword the paragraph naming the two retired identifiers to describe the
   same event by its shape ("the standing guard's per-file exemption table"
   / "the test pinning per-value exemption specificity") rather than by an
   identifier that no longer resolves. Do not change the substance of what
   is recorded -- only the identifiers that no longer exist.
3. Confirm `uv run pytest tests/test_contributing_calculators_doc.py -q`
   stays green (this is a comment-only change, no behavioural pin depends
   on it).

## Open questions

None.
