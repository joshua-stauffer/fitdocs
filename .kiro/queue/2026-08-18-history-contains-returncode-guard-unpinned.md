---
id: 2026-08-18-history-contains-returncode-guard-unpinned
title: _history_contains' returncode guard is unpinned, the same defect task 7.2 fixed in its siblings
status: open
importance: medium
importance_why: Same failure shape as two defects task 7.2 spent a review round closing, in the one sibling helper that lay outside its boundary.
effort: S
kind: gap
area: encumbered-content-purge, tests/test_forbidden_strings_source.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2 review round 3)
pinned_at: c3d2201
resume_command: "do: pin _history_contains' returncode guard in tests/test_forbidden_strings_source.py with a monkeypatched subprocess.run returning nonzero-with-populated-stdout, asserting the double is in effect, the way the four sibling helpers now do"
context:
  - tests/test_forbidden_strings_source.py
blocked_by: []
---

## What

`_history_contains` returns
`result.returncode == 0 and bool(result.stdout.strip())`. Deleting the
`returncode == 0` term leaves the module green. It is the same
indistinguishable-outcome shape that task 7.2 closed in `_root_commit_ids`
and `_commit_message`, in the one helper that sat outside 7.2's five-symbol
boundary.

## Why it matters

A `git` invocation that fails while writing something to stdout would be read
as a genuine history hit. In the pre-replacement era this module asserts a
history occurrence MUST be present, so the failure direction is a false pass
on the assertion that carries the era's whole point.

Bounded: the same reasoning that made the sibling guards observable applies
here, and the fix is now a known fifteen-line shape.

## Evidence

Reported by the task 7.2 reviewer, which ran it: mutating
`tests/test_forbidden_strings_source.py:224` from
`return result.returncode == 0 and bool(result.stdout.strip())` to
`return bool(result.stdout.strip())` left the module at 22 passed, 1 skipped.

Guard confirmed present at `dac1a7a`, line 224. Explicitly ruled out of task
7.2's scope (task 6.3 boundary) and left untouched by that task.

## How to pick it up

Copy the shape the four sibling tests now use: monkeypatch `subprocess.run`
to return `CompletedProcess(returncode=1, stdout="something\n")` against a
real repository, capture the unpatched result, assert the patched result
differs, then assert `False`. Verify the deletion mutation now reds. Done
when it does.
