---
id: 2026-08-13-build-rules-clone-instruction-contradicts-the-module
title: Task 7.2 forbids running build_rules against the --no-local clone, but the 6.4 guard redesign made it clone-independent and the module now says so
status: done
importance: high
importance_why: The two documents an operator reads before the one-shot, unrepeatable rewrite give opposite instructions about which repository the redaction spec files may be generated from. Whichever is wrong, the operator finds out during the one step in this spec that cannot be corrected afterwards.
effort: S
kind: inconsistency
area: encumbered-content-purge, scripts/purge/replacements.py
created: 2026-08-13
pinned_at: 439b38c
resume_command: "do: Reconcile tasks.md 7.2's 2026-08-09 clone amendment with build_rules' post-6.4 docstring. Read scripts/purge/replacements.py::build_rules and identity_leak_addresses first, then tasks.md 7.2's amendment bullet, then decide whether the prohibition is retired outright or retained as a belt-and-braces preference with its stated reason corrected."
context:
  - .kiro/specs/encumbered-content-purge/tasks.md
  - scripts/purge/replacements.py
  - .kiro/queue/2026-08-10-6-4-identity-derivation-guard-unsatisfiable.md
blocked_by: []
---

## What

`tasks.md` 7.2 carries an amendment dated 2026-08-09 (task 6.4's third review
round) instructing that `build_rules` **MUST NEVER** be run against the
`--no-local` clone, because that clone lacks the unreachable commit objects
`identity_leak_addresses`' orphaned-commit source depends on "for two of the
three real identity-leak addresses".

Task 6.4's remediation removed exactly that dependence. The orphaned-commit
source no longer contributes to the denylist at all — it is consulted only by
two guards — and the derivation now runs off reachable blob text plus the tip
tree, both of which every clone carries.

## Evidence

Verified in this run, on branch `impl/replacement-rules` (worktree
`../fitdocs-replacement-rules`, tip `eeab771` plus the uncommitted 6.4
remediation):

- `.kiro/specs/encumbered-content-purge/tasks.md:1118-1136` — "MUST be run
  against **the working repository itself** (or a same-filesystem
  `git clone --mirror` …). It must **NEVER** be run against the `--no-local`
  clone … That clone lacks the unreachable commit objects
  `identity_leak_addresses`' orphaned-commit source depends on for two of the
  three real identity-leak addresses".
- `scripts/purge/replacements.py:1461-1467` — "**`repo` may be any clone.** The
  identity denylist is derived from reachable blob text and the tip tree, both
  of which every clone carries; the unreachable-commit source only ever raises."
- The reviewer subagent built real `--mirror` and `--no-local` clones and
  measured the identical three-address denylist in all three repository states;
  `test_identity_denylist_is_identical_in_a_clone[mirror|no-local]` pins it.

The `tasks.md` bullet's stated *reason* is now false regardless of which
instruction is kept: the orphan source no longer supplies any of the three
addresses.

## Why it matters

7.2 is the one artifact in this spec that cannot be corrected after it runs, and
these are the two documents an operator reads immediately before running it. The
amendment also shapes the *order* of 7.2's steps — "generate the redaction spec
files from the working repository **before** creating the `--no-local` clone" —
so the contradiction is not merely descriptive.

## How to pick it up

1. Read `build_rules` and `identity_leak_addresses` in
   `scripts/purge/replacements.py`, including the stated limits of the two
   guards. Confirm for yourself that the orphan source contributes nothing.
2. Read the amendment bullet at `tasks.md:1118-1136`.
3. Decide between: (a) retire the prohibition, since the defect it was written
   against is gone; (b) keep it as a belt-and-braces preference, with the reason
   rewritten to something true — e.g. that the working repository is the tip
   7.1 freezes, which is the argument the
   `2026-08-12-tip-presence-sanctioning-is-order-sensitive` item is really
   about. (b) is likely the better answer, but its current justification cannot
   stand either way.
4. Whichever is chosen, the two documents must agree, and the ordering
   constraint in 7.2's steps must follow from the reason actually given.

## Done when

`tasks.md` 7.2 and `build_rules`' docstring state the same thing about which
repository the rule set may be generated from, and the reason given is one the
tests actually support.

## Resolution (2026-08-17, `impl/rewrite-preconditions` off `89b06b8`)

**The prohibition is retired, not reworded**, because the reason behind it is
false twice over — and the second half was only found by re-measuring rather
than by reading:

1. Task 6.4's remediation removed the dependence, as this item says.
2. `_orphaned_commit_identity_addresses` now returns **0** addresses in the
   *working repository* as well, and in a real `git clone --mirror` of it. The
   2026-08-09 pruning incident took the unreachable commits it reads. So the
   "belt and braces" reading of the amendment — keep it because the working
   repository is where guard 1 has something to corroborate against — is not
   available either. Guard 1 is vacuous in all three repository states.

Measured at tip `89b06b8` with `FITDOCS_FORBIDDEN_STRINGS` exported, against
the working repository, a real `--mirror` clone and a real `--no-local` clone:
all three derive the identical three-address denylist, **113** rules, and
byte-identical `render_rules` output (sha256 prefix `e3cd557b536b`). That is
strictly stronger than what `test_identity_denylist_is_identical_in_a_clone`
pins, which compares denylists rather than rendered rule sets.

**What replaces it** is the constraint that is actually true: the denylist's
sanctioning rule is tip-absence, so the rule set is a function of the tip it
is generated from, and that must be the tip the rewrite consumes. `tasks.md`
7.2 and `design.md` `#### HistoryRewrite` step 3 now both say the rules may be
generated from any of the three, recommend generating them **from the
`--no-local` clone after taking it** (which makes tip identity true by
construction), and require a `git rev-parse HEAD` equality assertion if they
are generated from the working repository instead. The ordering constraint
therefore follows from the reason given, and it is the reverse of the
2026-08-09 ordering, which followed from the reason that is now false.

Left open, and queued rather than fixed here:
`.kiro/queue/2026-08-17-orphan-source-claims-are-stale-after-the-pruning-incident.md`
— `_orphaned_commit_identity_addresses`' docstring still describes a
572-object population and claims both derived addresses "exist ONLY on
unreachable commits", and the pruning incident item still asserts that
`build_rules` raises against this repository and that Major 7 is blocked on it.
Measured today, it does not raise and Major 7 is not blocked on it.
