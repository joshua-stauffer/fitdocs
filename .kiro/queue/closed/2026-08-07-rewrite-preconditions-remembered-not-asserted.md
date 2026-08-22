---
id: 2026-08-07-rewrite-preconditions-remembered-not-asserted
title: Two rewrite preconditions rest on task 7.2 remembering them rather than asserting them
status: done
importance: medium
importance_why: The fresh-clone guarantee and the degenerate-merge case both decide correctness of a one-shot irreversible run, and neither is currently checked by anything.
effort: M
kind: gap
area: encumbered-content-purge, .kiro/specs/encumbered-content-purge/design.md
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (tasks 5.2, 5.3 reviews)
pinned_at: 7d49c84
resume_command: "do: Add the two missing rewrite preconditions to task 7.2's plan -- assert the clone is fresh and taken without the local optimisation before calling the driver, and decide whether the rewrite must also disable degenerate-merge pruning."
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/tasks.md
  - scripts/purge/rewrite.py
  - scripts/purge/plan.py
blocked_by: []
---

## What

Two separate gaps, both in the same place -- what task 7.2 must establish
before the rewrite runs.

First, the driver rewrites whatever repository it is handed and neither
produces nor asserts the fresh clone that Req 7.3 depends on. That guarantee
currently rests on 7.2 remembering to clone first.

Second, the design's invocation disables empty-commit pruning but not
degenerate-merge pruning, and task 5.2's would-be-pruned check does not model
the degenerate case at all.

## Why it matters

This spec rejects the remembered-rather-than-asserted shape explicitly, in task
5.5's own checklist bullet, and then relies on it here. A rewrite run against
an unclean or locally-optimised clone carries in the unreachable objects the
verification rows exist to prove absent -- and the fresh-clone row would then
pass against a subject that was never fresh.

The degenerate case is narrower but real: a merge whose post-removal tree
equals one parent's tree exactly is not flagged by the pruned check, and
nothing decides what the rewrite should do with it.

## Evidence

Task 5.3's driver takes the repository as an argument with no freshness
assertion; the reviewer confirmed nothing in the module or its tests
distinguishes a clone from the working repository. Task 5.2's reviewer
constructed a merge whose post-removal tree equals a parent's exactly and
observed the check not flag it; `commit_changed_paths`' docstring now documents
that gap.

## How to pick it up

Read task 7.2's bullets and design.md's Ordering steps. Add an assertion that
the clone is fresh -- fully packed, single remote, single-entry reflogs -- and
taken without the local optimisation, before the driver is called. Then decide
whether the invocation needs degenerate-merge pruning disabled too, and record
the decision either way. Done when no rewrite precondition depends on a human
remembering it.

## Open questions

Whether disabling degenerate-merge pruning is correct for this history, or
whether a degenerate merge should halt the run the way a would-be-pruned commit
does.

## Resolution (2026-08-17, `impl/rewrite-preconditions` off `89b06b8`)

**First gap — the fresh clone is now asserted.**
`scripts/purge/rewrite.py::assert_fresh_clone(repo)` is called by `run_rewrite`
itself, on a proceeding gate, before any command is emitted, and raises
`FreshCloneError` naming *every* property the repository lacks: no unreachable
object, no `objects/info/alternates`, fully packed, exactly one remote named
`origin`, single-entry reflogs, no stash, one worktree, every head equal to its
`origin` counterpart. The unreachable-object row is what makes it more than a
restatement of the tool's own sanity checks — it is "without the local
optimisation" expressed as a property of the *result* rather than as a flag
someone typed.

Validated against the real thing rather than a stand-in: the tests build real
`git clone --no-local` (accepted), `--local` (rejected — hardlinks the object
directory and carries the source's unreachable objects, confirmed independently
with `git fsck --unreachable`) and `--shared` (rejected — borrows objects
through an alternates file) clones of a source repository that genuinely holds
an unreachable commit, plus clones mutated after the fact (a commit, a second
remote, a stash, a second worktree, a stray branch). Every property was mutated
away individually and each mutation was caught by a named test, as was moving
the assertion after the spec-file guard and dropping it from `run_rewrite`
altogether.

**Second gap — the degenerate-merge question is closed by measurement, with no
flag added.** Measured with the real `git filter-repo` on a throwaway
repository built to hold exactly the case task 5.2's check does not model (a
merge whose post-removal tree equals one parent's tree exactly) plus a side
branch lying entirely inside the removal set:

- tool defaults: both the side commit and the merge are pruned; the commit map
  gains **two all-zeros rows**;
- this spec's invocation (`--prune-empty never`): **one row per pre-rewrite
  commit, no all-zeros row**, and the merge survives with **both parents**;
- `--prune-empty never --prune-degenerate never`: identical to the above.

The mechanism, read from the tool's source *after* measuring: `_prunable`
returns `False` immediately under `prune_empty == 'never'`, so nothing is
skipped, so `_SKIPPED_COMMITS` stays empty, and `_maybe_trim_extra_parents`
only ever drops a parent that was itself skipped. So `--prune-empty never`
covers the degenerate case as well as the empty one and the extra flag would be
a no-op — it is deliberately not added, and the decision plus its measurement
is recorded in `design.md` `#### HistoryRewrite`, `tasks.md` 7.2 and
`scripts/purge/rewrite.py`'s module docstring. Recorded honestly there too: for
the degenerate case the guarantee *does* rest on the hard-coded flag alone,
since 5.2's check does not model it. (This history also carries **zero** merge
commits across all 497 reachable commits at `89b06b8`; the decision does not
rest on that, since a merge could land before 7.2 runs.)

### Review round 2 (2026-08-17) — one half-asserted property, one dead term

- **Property 8 was half-asserted.** Only the `counterpart is None` branch was
  pinned; replacing the *inequality* branch with `elif False:` left the whole
  suite green — on the one-shot gate. Now pinned by a clone whose local head
  has moved while its reflog stays single-entry. The head is moved by writing
  the loose ref file directly, because `git update-ref` appends to
  `logs/refs/heads/main` even under `-c core.logAllRefUpdates=false` (git also
  logs whenever the reflog file already exists, and a clone's does) — that
  second reflog entry would have rejected the fixture on its own and made the
  isolation false.
- **The `for-each-ref` union in `_unreachable_object_ids` was both
  unfalsifiable and falsely justified.** Its stated reason was that
  `git rev-list --objects` does not print annotated tag object ids. Measured on
  a repository with an annotated tag: it does (`<tag-object-id> v1`), and
  `--all` means every ref under `refs/` in any case. The term is removed rather
  than re-justified, with the measurement recorded where the claim was.
- The `--reflog` term on the same reachable side survived mutation too, but its
  reason is true (a reflog entry is a real pin). It cannot be falsified through
  `assert_fresh_clone` — any repository where it matters already fails the
  single-entry-reflog row — so it is now pinned directly against the helper,
  on a source whose amended-away commit is reachable only from the reflog.

Three false claims in the same code were corrected by execution: that nothing
but the unreachable objects rejects a `--local` clone (it is also not fully
packed — 9 loose objects); that without the fixture's amend both clone shapes
would look identical (they do not — `--local` is still rejected on loose
objects, so the amend is needed for the unreachable row alone, and that is now
the control that isolates it); and a claimed count anchor that was not in the
body. The anchor is now real, and the measured count is **six**, not the three
the prose implied.
