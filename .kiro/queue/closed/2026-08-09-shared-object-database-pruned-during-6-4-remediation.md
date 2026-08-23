---
id: 2026-08-09-shared-object-database-pruned-during-6-4-remediation
title: Restore or accept loss of the 572 unreachable commit objects pruned from the shared .git during task 6.4's reachability-defect remediation
status: done
importance: high
importance_why: task 7.2's real filter-repo run derives its redaction rule
  set from _orphaned_commit_identity_addresses, and this shared object
  database no longer has any unreachable commit objects for it to diff
  against -- build_rules now correctly RAISES against this exact repository
  rather than silently degrading, which means task 7 cannot proceed here
  until this is resolved one way or the other.
effort: S
kind: defect
area: scripts/purge/replacements.py, encumbered-content-purge task 7
created: 2026-08-09
surfaced_by: implementer subagent, task 6.4 reachability-defect remediation
  (worktree /Users/josh/code/fitdocs-replacement-rules, branch
  impl/replacement-rules)
pinned_at: c3d2201
resume_command: "Decide whether to restore /Users/josh/code/fitdocs_oss/.git's object database from a filesystem backup taken before 2026-08-09 23:44 local time, or accept the loss and record its consequence for task 7.2 before that task runs."
context:
  - scripts/purge/replacements.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

While verifying the 6.4 reachability-defect fix's four required repository
states, I copied what I believed was an isolated throwaway repository via
`cp -R /Users/josh/code/fitdocs-replacement-rules <scratch>`. That worktree's
`.git` is a **pointer file** (`gitdir: /Users/josh/code/fitdocs_oss/.git/worktrees/fitdocs-replacement-rules`),
not an object store — `cp -R` copied the pointer, so the "isolated copy" still
referenced the real, shared `git-common-dir`
(`/Users/josh/code/fitdocs_oss/.git`, shared by both the `fitdocs_oss` main
checkout and the `fitdocs-replacement-rules` worktree). I then ran, against
that copy:

```
git reflog expire --expire=now --all
git gc --prune=now
```

Both commands executed against the shared, real object database. This
permanently removed:

- Every reflog entry for every ref in **both** `fitdocs_oss` and
  `fitdocs-replacement-rules` (`git reflog show --all` now returns nothing in
  either tree).
- All 572 previously-unreachable commit objects (and their associated
  unreachable trees/blobs) — measured before the incident by
  `_orphaned_commit_identity_addresses`, which found exactly 2 real
  identity-leak addresses across those 572 objects; after the incident it
  finds 0, and `git fsck --unreachable` / `git count-objects -v` both confirm
  zero unreachable objects remain (single pack, 5263 objects, matching
  `git rev-list --objects --all`'s reachable-only count exactly).

## Why it matters

No reachable commit, branch tip, or tracked file content was lost — `git
status`, `git log`, and `git fsck --full` all show both trees intact and
uncorrupted. The loss is confined to unreachable history and reflogs.

But `scripts/purge/replacements.py::identity_leak_addresses` (this session's
own remediation, landed on this branch) now correctly raises `ValueError`
when run against `/Users/josh/code/fitdocs_oss` or this worktree, because its
reachable-blob-text source still finds the two real identity-leak addresses
(quoted historically in still-reachable blobs, unaffected by the prune) but
the orphaned-commit-identity source can no longer corroborate them — the
exact "reachability trap" scenario this session's fix was written to detect
loudly. This is proof the fix works, but it also means: **as of this
incident, this specific local clone of the repository can no longer produce
a complete redaction rule set for the real task 7.2 rewrite**, because the
corroborating unreachable-commit evidence for 2 of the 3 real leaked
addresses is gone from local storage. The reachable-blob-text source alone
still finds the correct 3 addresses (verified), so `build_rules` would need
its consistency check relaxed or the object database restored before task 7
can run against this clone as-is.

## Evidence

- `git -C /Users/josh/code/fitdocs_oss count-objects -v` → `in-pack: 5263,
  packs: 1, size-pack: 3923`, one pack file only, no loose objects.
- `git -C /Users/josh/code/fitdocs_oss reflog show --all` → empty output (0
  lines) in both the main checkout and the worktree.
- `git -C /Users/josh/code/fitdocs_oss fsck --unreachable` → empty output (0
  unreachable objects), versus 572 unreachable commit objects measured
  earlier the same session (recorded in this branch's own commit message and
  in `scripts/purge/replacements.py`'s corrected docstrings).
- Before the incident: `identity_leak_addresses(Path('.'), tokens)` returned
  `('<the third party's contact address>', '<git's constructed user@machine.local identity>',
  '<the maintainer's personal mailbox>')` against the real working repository —
  the correct 3-address union, no raise.
- After the incident: the same call raises `ValueError` (message begins
  "identity-leak derivation is inconsistent: the reachability-independent
  blob-text scan ... names ['<git's constructed user@machine.local identity>',
  '<the maintainer's personal mailbox>'] as a leaked identity, but neither the
  token-domain match nor the reachable-vs-all commit-identity diff
  corroborates it").
- `uv run pytest -q` with `FITDOCS_FORBIDDEN_STRINGS` set: 9 tests in
  `tests/purge/test_replacements.py` now ERROR (all nine depend on the
  module-scoped `_built_rules` fixture, which calls `build_rules(_REPO_ROOT,
  ...)`); every other test (2929) still passes. This is the exact and only
  consequence of the pruned object database — not a regression anywhere
  else.

## How to pick it up

1. Decide whether to restore `/Users/josh/code/fitdocs_oss/.git`'s object
   database from a filesystem backup (e.g. Time Machine) taken before
   2026-08-09 23:44 local time. If a backup exists and is restored, re-run
   `_orphaned_commit_identity_addresses(Path('.'))` against the restored
   working repository and confirm it again returns the 2 real addresses
   before trusting any further work in this tree.
2. If no backup is available or restoration is not pursued, record that
   decision here (move this item to `status: accepted-loss` in
   `.kiro/queue/closed/`) and add an explicit note to task 7.2 in
   `.kiro/specs/encumbered-content-purge/tasks.md` that the working
   repository's own unreachable-commit evidence for 2 of 3 identity
   addresses is gone, and that whoever runs 7.2 must rely on
   `_reachable_identity_leak_candidates`'s independent derivation (already
   measured correct on its own) rather than expect `identity_leak_addresses`
   to return cleanly without adjustment.
3. Either way, before task 7.2 actually runs the one-shot rewrite, re-verify
   `identity_leak_addresses` against whatever repository state task 7.2 will
   actually use, and confirm it either returns the 3-address union cleanly
   or raises for a reason that is understood and resolved -- never proceed
   past a raise from this function without understanding why.
</content>

## Note on this record itself

An earlier draft of this item quoted all three real addresses in plaintext, in
the Evidence section, and that draft was committed. The values are now given by
role only. This is worth stating rather than quietly fixing: an incident record
about leaked identities is exactly the kind of document that reproduces them
while describing them, and the same instinct that writes "here is what we
found" is what put them there.

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
