---
id: 2026-08-08-commit-identity-env-override-undetected
title: The commit-identity precondition checks only git config, so GIT_AUTHOR_EMAIL / GIT_COMMITTER_EMAIL silently defeat it
status: done
importance: medium
importance_why: Req 5.3 is asserted on every post-rewrite commit; an environment override wins over both config scopes and the assertion passes anyway, so the personal address lands in the author and committer headers with the gate reporting success.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/adopt.py, .kiro/specs/encumbered-content-purge/design.md
created: 2026-08-08
surfaced_by: /kiro-impl encumbered-content-purge (task 5.5 review, round 1)
pinned_at: c3d2201
resume_command: "do: Decide whether the CloneAdoption identity precondition must also assert the absence of GIT_AUTHOR_EMAIL / GIT_COMMITTER_EMAIL / EMAIL in the environment, and amend design.md's `#### CloneAdoption` 'Asserted precondition, not luck' subsection before changing scripts/purge/adopt.py -- the current narrow check matches what the design prescribes, so this is a design-level gap, not an implementation defect."
context:
  - scripts/purge/adopt.py
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/requirements.md
blocked_by: []
---

## What

`assert_commit_identity` in `scripts/purge/adopt.py` reads `git config --local
user.email` and `git config --global user.email` and compares each against the
non-personal address. Git resolves the identity it actually stamps from a wider
set of sources than that: `GIT_AUTHOR_EMAIL` and `GIT_COMMITTER_EMAIL` override
`user.email` in *both* scopes, and `EMAIL` is consulted when no config value
exists at all.

So a shell holding `GIT_AUTHOR_EMAIL=<personal address>` passes the
precondition and then writes that address into every commit the post-rewrite
work produces.

## Why it matters

Task 5.5's own reasoning for checking both scopes is that a fresh clone
inherits global configuration, making this "the single setting whose drift
would silently violate Req 5.3 on every post-rewrite commit". The environment
is a second, wider inheritance path with the same consequence and no check at
all. The whole point of the assertion is that identity correctness must not
rest on luck.

The window is Major 8, where the post-rewrite commits are made — after the old
repository has been destroyed, so a wrong address cannot be repaired by
redoing the rewrite.

## Evidence

`scripts/purge/adopt.py::assert_commit_identity` and `_git_config_value` issue
exactly `git config --local user.email` and `git config --global user.email`;
neither inspects `os.environ` for the override variables. The 5.5 reviewer
raised this as a follow-up after confirming the two config scopes themselves
are correctly and independently pinned.

`design.md`'s `#### CloneAdoption` "Asserted precondition, not luck" subsection
prescribes only `git config user.email`, so the implementation matches the
approved design. That is why this is filed as a design gap rather than a
defect: the module did what it was told.

## How to pick it up

Read `design.md`'s `#### CloneAdoption` "Asserted precondition, not luck"
subsection and Req 5.3 first, then `scripts/purge/adopt.py::assert_commit_identity`
and its five tests in `tests/purge/test_adopt.py`.

Confirm the override precedence by running it rather than trusting this item:
set `GIT_AUTHOR_EMAIL` in a scratch repository whose `user.email` is something
else, make a commit, and read `git log --format='%ae %ce'`. Check `EMAIL` too,
and check whether `GIT_COMMITTER_EMAIL` and `GIT_AUTHOR_EMAIL` differ in
precedence.

Done when either the design prescribes the wider check and the module asserts
it with a violating fixture per variable, or the decision to keep the narrow
check is recorded with its reason.

## Open questions

Whether the assertion should *clear* the offending variables rather than halt.
Halting is consistent with every other gate in this spec, but the operator will
be running a one-shot procedure and a halt that cannot be satisfied without
leaving the session is a different cost than the other halts carry.

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
