---
id: 2026-08-07-conftest-cache-proofing-misses-scripts
title: The root conftest cache-proofs src/ only, while this spec's production code lives in scripts/
status: done
importance: high
importance_why: A mutation that appears not to take effect reads as an assertion that does not discriminate, which is the exact wrong conclusion and the one this repo's protocol is built to prevent. Raised to high on 2026-08-08: the workaround has now had to be carried in every task brief and every review brief for Majors 4 and 5, and a reviewer measured the stale entries directly.
effort: S
kind: gap
area: steering, conftest.py, .kiro/steering/change-protocol.md
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (task 5.1 review)
pinned_at: c3d2201
resume_command: "do: Extend the root conftest.py's bytecode cache-proofing to cover scripts/ as well as src/, then confirm a single-character mutation under scripts/purge/ takes effect on a same-second revert without clearing __pycache__ by hand."
context:
  - conftest.py
  - .kiro/steering/change-protocol.md
  - scripts/purge/
blocked_by: []
---

## What

The root `conftest.py` makes pytest runs cache-proof for `src/` only. Every
module this spec produced lives under `scripts/purge/`, outside that cover.

## Why it matters

`change-protocol.md`'s Fixture Discrimination section requires every assertion
to be proven capable of failing by mutation, and warns that CPython validates
cached bytecode on mtime and size -- which single-character mutations routinely
leave unchanged. Uncovered, a mutation reverted inside the same filesystem
second can keep running the cached code, the suite stays green, and the author
concludes the assertion does not discriminate. That is the failure direction
the protocol names as the one that hurts. Every implementer and reviewer on
Majors 4 and 5 had to clear `scripts/purge/__pycache__` by hand before each
mutation, and that instruction had to be repeated in every task brief.

## Evidence

`conftest.py` derives its cache-proofing root from a `src` path. A stale
`scripts/purge/__pycache__` entry was present in the worktree at the start of
task 5.1's remediation, dated several days earlier. Six separate task briefs in
this run carried a manual "clear the cache first" instruction as a workaround.

## How to pick it up

Read `conftest.py`'s cache-proofing block and note how it selects its root.
Extend it to cover `scripts/` alongside `src/`. Verify by mutating a single
character under `scripts/purge/`, running the suite, reverting within the same
second, and running again -- the second run must observe the reverted code
without any manual cache clearing. Done when the manual step can be dropped
from future task briefs.

## Progress, 2026-08-08

Still open, and the manual workaround is now universal rather than occasional:
tasks 5.5, 5.6 and 5.7 each carried "clear `scripts/purge/__pycache__` before
every mutation run" in both the implementer and the reviewer brief, and two
reviewers recorded doing it before every single mutation.

Task 5.6's reviewer measured the stale entries directly, finding live
`pins.cpython-311.pyc` and `adopt.cpython-311.pyc` under
`scripts/purge/__pycache__` during review, and noted that
`sys.dont_write_bytecode = True` stops the *pytest* interpreter writing new
files but does not clear what a stray `uv run python -c`, an editor, or any
other interpreter already left there.

Two further facts worth carrying into the fix:

- The existing `assert _SRC.is_dir()` guard is load-bearing and must be
  preserved per root. It exists so the walk cannot silently scan nothing --
  the vacuous-walk anti-pattern this repo names. A widened walk needs the same
  assertion for each root, or it goes silent exactly when a directory is
  renamed.
- The perimeter is now defined in two places that can drift: this file and
  `pyproject.toml`'s `[tool.mypy] files` list. Deriving both from one source
  would prevent a directory entering the type-checking perimeter while staying
  outside the cache-proofing one, which is precisely how `scripts/` ended up
  here.

A duplicate of this item was opened on 2026-08-08 as
`2026-08-08-bytecode-cache-proofing-misses-scripts` by a session that did not
find this one, and was dropped in favour of this item; its evidence is folded
in above.

## Open questions

Whether the perimeter should be derived from a single source of truth shared
with `pyproject.toml`'s `[tool.mypy] files` list, so a directory added to one
cannot be missing from the other. That list already carries a warning about
adding modules to it in the same change as fixing their errors; a second
consumer would need the same discipline.

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
