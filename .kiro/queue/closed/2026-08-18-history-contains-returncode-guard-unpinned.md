---
id: 2026-08-18-history-contains-returncode-guard-unpinned
title: _history_contains' returncode guard is unpinned, the same defect task 7.2 fixed in its siblings
status: done
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

## Resolution

**Closed `done` 2026-08-23 — the subject was retired, and retirement is the
resolution.** Post-purge queue triage after `encumbered-content-purge`
completed (spec 57/57, `87ce085`).

This item's subject was the purge's own one-shot tooling: a module under
`scripts/purge/`, a test under `tests/purge/`, or a precondition on a purge
task that has since run. Task 9.3 (`c18ec26`) deleted `scripts/` entire and
`tests/purge/` less three relocations; `ls scripts/ tests/purge/` errors on
`HEAD`. The operation those modules governed — sweep, redact, replace, adopt,
verify — executed to completion and is not repeatable: the history replacement
is a fresh root (`c3d2201`) with no mapping by construction.

There is therefore no future run for this defect to affect, and no code left to
carry it. The retirement record is `docs/reference/history-rewrites.md` § 8.

Checked before closing: the item's subject does not survive in the three
relocated guards (`tests/_forbidden_strings.py`, `tests/test_forbidden_strings.py`,
`tests/_content_oracle.py`). Items whose subject *did* survive were kept open
in the same triage.
