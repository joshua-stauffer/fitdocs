---
id: 2026-08-22-archive-readable-check-treats-dangling-objects-as-corruption
title: _assert_archive_readable treats git fsck's informational "dangling" stdout as failure, so it reds on any real archive
status: done
importance: medium
importance_why: It fired on the real Major 8 run AFTER the swap had completed, raising ArchiveNotReadableError on an archive that is provably sound — and because dangling objects are normal in an archived .git whose branches were deleted, it can be expected to fire on any real archive rather than only this one.
effort: S
kind: bug
area: scripts/purge, encumbered-content-purge
created: 2026-08-22
surfaced_by: Major 8 task 8.2, the real replacement run
pinned_at: c3d2201
resume_command: "do: narrow scripts/purge/replace.py::_assert_archive_readable so git fsck's informational dangling-object lines do not read as corruption, and pin the distinction with a test"
context:
  - scripts/purge/replace.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`scripts/purge/replace.py::_assert_archive_readable` ends with:

    if fsck.returncode != 0 or fsck.stdout.strip() or fsck.stderr.strip():
        raise ArchiveNotReadableError(...)

`git fsck --connectivity-only` prints **informational** `dangling <type>
<oid>` lines on **stdout** while exiting **0**. Any unreachable-but-intact
object produces one. So a sound archive reds.

Measured on the real task 8.2 run, 2026-08-22:

- `git --git-dir=<archive> fsck --connectivity-only` → **exit 0**, **stderr
  empty**, stdout eight `dangling` lines
- filtering those lines leaves **no output at all**
- `git --git-dir=<archive> cat-file -e <old tip>` → exit 0
- `git --git-dir=<archive> rev-list <old tip> --count` → **525**

Every dangling object was explainable: two stash WIPs, several superseded
commits from branches deleted after merge, and the forged root of the run's
own first, halted attempt.

## Why it matters

The raise happened **after the swap had already completed** — both
`move_clone` calls had run, so the working repository was already on the
fresh root and the old `.git` was already archived. `run_replace` had no
work left but `return 0`. The exception therefore reported a failure of the
exact property it had just established, at the one moment the operator is
most primed to treat any error as a reason to swap back.

This is not specific to the 2026-08-22 run. An archived `.git` is precisely
the kind of repository that accumulates unreachable objects — merged branches
deleted, stashes dropped, refs expired — so **the normal case for this check
is to fire**. A future operator who trusts it will either swap back a good
replacement or learn to ignore the check, and the second is worse.

Note the check's *first* half is well designed and should be preserved: the
`cat-file -e` versus `rev-parse --verify` distinction is load-bearing and
documented at length in the docstring. Only the fsck predicate is wrong.

## How to pick it up

Narrow the predicate to real failure signals: non-zero exit, non-empty
stderr, or stdout lines that are **not** `dangling …`. `git fsck` reports
genuine corruption as `missing`/`broken link`/`error:` and returns non-zero,
so the exit code plus a dangling-filtered stdout is the honest test.

Pin the distinction with two fixtures, and prove each by mutation:

1. an archive with a dangling object → must **pass**, and reverting the fix
   must red it (this is the case that fired);
2. an archive with a genuinely broken link or missing object → must **fail**,
   so the narrowing does not blind the check.

The second fixture is the one that matters: a fix that simply drops the
stdout condition passes fixture 1 and silently weakens the gate, which is the
same "updating a pin is where guards die" trap this spec has hit repeatedly.

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
