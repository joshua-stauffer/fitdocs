---
id: 2026-07-29-sdist-guard-rename-evadable
title: A rename ships both unlicensed extracted tables in the sdist with the full suite green
status: done
importance: high
importance_why: This is a licensing surface, not defence-in-depth. Renaming the extracted tables' directory put two CSVs carrying the third party's copyright notice into a publishable artifact with 2090 tests passing and nothing to warn the session that moved them.
effort: M
kind: gap
area: training-load, tests/load/test_packaging.py, pyproject.toml
created: 2026-07-29
surfaced_by: adversarial review of the branch that added the sdist exclusion for the withdrawn methodology's tables (queue-top7 batch)
pinned_at: 0080811
resume_command: "do: make the sdist withdrawal guard content-keyed rather than path-literal — scan archive members' CONTENT against _WITHDRAWN_TABLE_VALUES instead of matching on the writeup's and the extracted tables' literal paths — so a rename cannot ship the tables [queue: .kiro/queue/2026-07-29-sdist-guard-rename-evadable.md]"
context:
  - tests/load/test_packaging.py
  - pyproject.toml
  - .kiro/queue/2026-07-26-withdrawal-guards-evadable-by-rename.md
  - .kiro/queue/2026-07-27-withdrawal-evasions-one-level-up.md
blocked_by: []
---

## What

The sdist exclusion landed in `0080811` closes the reported hole, but both the
`pyproject.toml` exclude and the new guard in `tests/load/test_packaging.py`
are keyed to **literal paths**. Renaming the directory defeats both at once:
the exclude stops matching, so hatchling packages the files, and the guard
stops matching, so nothing reds.

## Why it matters

Two existing queue items already track rename-evasion in the withdrawal guards
(`2026-07-26-withdrawal-guards-evadable-by-rename`,
`2026-07-27-withdrawal-evasions-one-level-up`). Neither contemplates the sdist,
because the sdist guard did not exist when they were written. This one is a
notch more serious than either: those are defence-in-depth on a settled
withdrawal, this one puts unlicensed third-party data into an artifact intended
for PyPI. The failure is also silent in the worst way — the session that renames
the directory is doing something innocuous and gets a fully green suite.

## Evidence

Reproduced by the reviewer on the branch that added the sdist exclusion for the
withdrawn methodology's tables, at the state that
merged:

```
$ git mv <the extracted tables' directory> <a renamed copy>   # no other change
$ uv build --sdist && tar tzf dist/*.tar.gz | grep <the renamed copy>
fitdocs-0.1.0/<the renamed copy>/<first extracted-table file>
fitdocs-0.1.0/<the renamed copy>/<second extracted-table file>
$ uv run pytest -q
2090 passed
```

A renamed copy of the writeup also escapes this
guard, though it is incidentally caught by the pre-existing
`tests/test_docs_guarantees.py::test_no_shipped_documentation_presents_the_withdrawn_methodology_as_available`.

The path literals are at `tests/load/test_packaging.py:391-399`; the exclude
list is at `pyproject.toml:36-38`.

## How to pick it up

1. Read `tests/load/test_packaging.py:321-425` (the sdist guard as merged) and
   `:189-197` (the deleted writeup-sourced-constant test, which
   already reads the writeup's content and holds `_WITHDRAWN_TABLE_VALUES`).
2. The durable shape is content-keyed: open each archive member and test its
   bytes against `_WITHDRAWN_TABLE_VALUES` rather than testing its name. That fires
   once regardless of where the file moves, and it also covers the two sibling
   rename items' concern in the same mechanism.
3. Note the reviewer's warning about the narrower scoping: a blanket
   substring match over sdist member NAMES for the third party's name produces
   false positives, because
   the sdist legitimately carries `.kiro/queue/` prose naming the third party. Content
   matching on the table VALUES does not have that problem.
4. Done looks like: the reproduction above reds, and the false-positive prose
   files still pass.

## Open questions

Whether this should absorb the two sibling rename items into one content-keyed
guard, or stay a third separate mechanism. The reviewer on the sibling item
suggested a shape-keyed AST scan that "fires once instead of 21 times as
sibling specs land" — worth reconciling all three before implementing.

## Resolution

**Status: done. Closed 2026-07-30**, merged to `main` at `f0dbf2b`
(branch: the content-keyed sdist guard, 4 commits), validated after rebase:
2297 passed, ruff + format + mypy clean, no `dist/` left behind.

The sdist guard in `tests/load/test_packaging.py` is now **content-keyed**: it
opens every archive member and tests its bytes against fingerprint values from
the withdrawn tables, rather than matching member names. A rename can no longer
ship the encumbered CSVs.

### Verified on `main` at close time — the item's own reproduction

```
$ git mv <the extracted tables' directory> <a renamed copy>
$ uv run pytest tests/load/test_packaging.py -q
1 failed, 5 passed
E   assert not ['fitdocs-0.1.0/<the renamed copy>/<first extracted-table file>',
                'fitdocs-0.1.0/<the renamed copy>/<second extracted-table file>']
```

Restored with `git mv` back; tree clean. Both the rename reproduction and the
tuple-emptying attack were re-run by the closing session directly, not taken
from the implementation transcript.

### What it cost, and why that matters to the next editor

**Four review rounds, and each round found a different mutation that left the
guard blind with the full suite green:**

| mutation | suite | after rename |
|---|---|---|
| `fileobj.read(0)` | 2286 passed | both CSVs ship |
| `fileobj.readline()` | 2286 passed | both CSVs ship |
| truncate `_WITHDRAWN_CONTENT_FINGERPRINTS` | 2286 passed | both CSVs ship |
| empty the two source tuples | 2286 passed | both CSVs ship |

Each fix was one level narrower than the defect, and the next round found the
sibling route. The invariants now in place, none of which should be weakened
without re-running all four: `bytes_inspected == expected_bytes` (exact, not
`> 0`); a superset assert tying the composite to its source tuples; non-empty
asserts on **all** fingerprint tuples; an **exact-match** self-exemption (never
`endswith`); and a rename-tolerant read-back over the extracted tables' directory pinning
the fingerprints to the real tables.

### Scope: the two sibling items stay open, with reasons

- **Absorbed**: evasion 3 of `2026-07-27-withdrawal-evasions-one-level-up` (the
  two largest tables pasted verbatim into an allowlisted module) is now caught,
  mutation-verified. Evasion 2 is incidentally closed **for the sdist artifact**
  because the sdist ships the whole tree.
- **Not absorbed**: `2026-07-26-withdrawal-guards-evadable-by-rename`'s residue
  is a renamed calculator *class* — a shape with no literal to match, which no
  content fingerprint can reach. Evasion 1 is the same. The reviewer independently
  judged this sound reasoning rather than a rationalization; both items remain
  open and want an AST/shape scan, not this mechanism.

### Two gaps this close does NOT cover

1. **The guard is not on the publish path.** It is a pytest test, and this repo
   has no CI — no `.github`, no workflow YAML anywhere. `uv build && uv publish`
   bypasses it entirely. Tracked at
   `.kiro/queue/2026-07-30-no-release-gate-on-the-publish-path.md` (high).
2. **The guard proves absence and never proves its matcher can find anything.**
   All four mutations above break exactly that property; one positive control
   would have caught them all. Tracked at
   `.kiro/queue/2026-07-30-sdist-guard-has-no-positive-control.md`.

### Note for the encumbered-content purge

This guard's detection data **is** encumbered content — nine literals
transcribed verbatim from the writeup and the CSVs. After a purge they would be
the last data derived from the withdrawn methodology in the repo, sitting in
the file whose job is
keeping such data out. The read-back added in round 3 also fails closed when the
CSVs are deleted, by design. `.kiro/specs/encumbered-content-purge/` owns the
oracle decision; salted hashes were suggested, at the cost of the read-back
property.

**Superseded 2026-08-01**: `encumbered-content-purge` task 3.1 deleted the
writeup and both extracted tables from the working tree entirely, per
Requirement 4's reversal of their retention. Task 4.1 of that same spec
re-bases this guard's detection data onto the value oracle and retires its
remaining token-literal detections.
