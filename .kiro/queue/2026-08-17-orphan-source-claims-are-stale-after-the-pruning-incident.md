---
id: 2026-08-17-orphan-source-claims-are-stale-after-the-pruning-incident
title: Three places still describe the orphan-commit identity source as it was before the 2026-08-09 pruning incident, including one that says task 7 is blocked
status: open
importance: medium
importance_why: One of the stale claims is a queue item's own importance_why asserting that build_rules RAISES against this repository and that "task 7 cannot proceed here until this is resolved". Measured today it does not raise and task 7 is not blocked by it, so an operator triaging the queue before the one-shot rewrite is told to stop for a reason that no longer exists.
effort: S
kind: inconsistency
area: encumbered-content-purge, scripts/purge/replacements.py, .kiro/queue
created: 2026-08-17
surfaced_by: /kiro-impl encumbered-content-purge (rewrite-preconditions, verifying the 2026-08-13 build_rules clone-instruction item)
pinned_at: 89b06b8
resume_command: "do: Re-measure _orphaned_commit_identity_addresses and the unreachable-object population against the current working repository, then correct the three stale claims listed in the Evidence section -- the two in scripts/purge/replacements.py's docstrings and the two in .kiro/queue/2026-08-09-shared-object-database-pruned-during-6-4-remediation.md's front matter and body."
context:
  - scripts/purge/replacements.py
  - .kiro/queue/2026-08-09-shared-object-database-pruned-during-6-4-remediation.md
blocked_by: []
---

## What

The 2026-08-09 pruning incident removed the unreachable commit objects
`_orphaned_commit_identity_addresses` reads. Task 6.4's remediation made the
denylist independent of that source, and both facts are recorded. What is not
recorded is that several *specific numeric and consequential* claims written
before the incident are now false, and one of them tells a reader that task 7
is blocked.

## Evidence

Measured in worktree `../fitdocs-rewrite-preconditions` at tip `89b06b8`, with
`FITDOCS_FORBIDDEN_STRINGS` exported. Addresses named only by the 8-hex
SHA-256 tag `_masked_address` produces.

1. `_orphaned_commit_identity_addresses(Path("/Users/josh/code/fitdocs_oss"))`
   returns **0** addresses. It returns 0 in a real `git clone --mirror` of the
   working repository too — the mirror hardlinks the object directory, so this
   is not a clone artefact.
2. The working repository holds **505** commit objects of which **497** are
   reachable: **8** unreachable commits, **30** unreachable objects in total
   (`git cat-file --batch-all-objects` minus `git rev-list --objects --all`).
   None of their author/committer addresses is absent from the reachable set,
   which is why (1) is empty rather than merely small.
3. `build_rules` **does not raise** against the working repository. It returns
   **113** rules and a three-address denylist (tags `2500d120`, `cd8f2c1f`,
   `1a7d8227`) — identical, and byte-identical after `render_rules` (sha256
   prefix `e3cd557b536b`), in the working repository, a `--mirror` clone and a
   `--no-local` clone.

Against that, the stale claims:

- `scripts/purge/replacements.py`, `_orphaned_commit_identity_addresses`'
  docstring: "the maintainer's own address and the git-constructed
  `NAME-at-HOST.local` machine-hostname form ... **Both exist ONLY on
  unreachable commits**" and "see `_iter_all_local_objects`' corrected
  docstring for the real population -- **572 unreachable commit objects**".
  Neither holds now: the population is 8 unreachable commits, and this
  function finds nothing on them.
- `.kiro/queue/2026-08-09-shared-object-database-pruned-during-6-4-remediation.md`,
  `importance_why`: "**build_rules now correctly RAISES against this exact
  repository** rather than silently degrading, which means **task 7 cannot
  proceed here** until this is resolved one way or the other." Measured in (3),
  it does not raise, and 6.4's polarity correction is precisely why — guard 1
  is vacuously satisfied wherever the orphan source is empty, which
  `identity_leak_addresses`' own docstring already states.
- The same item's body: "zero unreachable objects remain (single pack, 5263
  objects, matching `git rev-list --objects --all`'s reachable-only count
  exactly)". True on 2026-08-09; 30 unreachable objects have accumulated since,
  from ordinary worktree work.

## Why it matters

The pruning item is `importance: high` and reads as a blocker on Major 7. The
next session to triage the queue before task 7.2 — the one-shot, unrepeatable
rewrite — is told by it to stop and restore an object database from backup
first. That is no longer necessary, and acting on it (restoring a pre-incident
object database) would reintroduce 572 unreachable commits carrying the
personal address into the repository the rewrite is about to clone from.

The docstring claims matter for a narrower reason: they are the recorded
justification for keeping the orphan source at all, and a reader checking that
justification against the repository finds it contradicted.

## How to pick it up

1. Re-measure (1), (2) and (3) yourself — the numbers above are a snapshot of
   an accumulating population and (2) in particular will have drifted.
2. Correct the two `replacements.py` docstrings to say what the source found
   *when it was measured*, with the date, rather than what it finds now.
3. Decide the pruning item's status: it is arguably `resolved-by-measurement`
   (the loss is accepted and no longer blocks anything) rather than `open`, but
   the decision belongs to whoever owns the restore-or-accept call, and the
   record of what was lost must stay either way.

## Open questions

- Does anything still depend on the orphan source being non-empty? Guard 1
  becomes unfalsifiable while it is empty, so the "loud, not silent" posture
  task 6.4 established is currently inert — worth stating explicitly wherever
  that posture is claimed.
