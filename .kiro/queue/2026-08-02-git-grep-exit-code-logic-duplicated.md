---
id: 2026-08-02-git-grep-exit-code-logic-duplicated
title: The git-grep exit-1-vs-real-error split exists twice in sweep.py and can diverge
status: open
importance: medium
importance_why: Two copies of the rule that separates "no match" from "the search broke"; a fix applied to one leaves the other silently reading a failure as a clean sweep.
effort: S
kind: inconsistency
area: encumbered-content-purge, scripts/purge/sweep.py
created: 2026-08-02
surfaced_by: /kiro-impl encumbered-content-purge (task 3.2, reviewer round 3)
pinned_at: 9612d28
resume_command: "do: read scripts/purge/sweep.py lines 314-318 and 448-452, decide whether run_identity_probe_sweep can share _git_grep_files without changing that helper's -l -z contract, and either factor the exit-code split into one helper both call or add a comment at each site naming the other"
context:
  - scripts/purge/sweep.py
  - tests/purge/test_sweep.py
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`scripts/purge/sweep.py` carries the git-grep exit-code rule twice. `_git_grep_files`
implements it at lines 314-318, and `run_identity_probe_sweep` implements it again at
lines 448-452. Both encode the same non-obvious fact: `git grep` exits **1** for "no
match found", which is a normal result, and non-zero-non-1 for a real failure, which
must raise rather than be read as an empty result set.

The duplication is justified rather than accidental — the identity probe needs `-nPoI`
match output, while `_git_grep_files` returns a `-l -z` path list, so sharing the helper
outright would change its contract. But the rule itself is now stated in two places with
nothing tying them together.

## Why it matters

This rule is exactly the "swallowed failure" species that has cost this spec four review
rounds across three tasks. If the split is ever corrected in one copy — a new exit code
handled, the boundary moved — the other copy keeps the old behaviour, and the failure
mode is silent: a broken search returns an empty tuple, which is indistinguishable in the
inventory from a clean sweep. That is the precise outcome `tasks.md`'s execution rules
warn about ("the extended-regex mode ... returns empty, which reads as a clean sweep").

Both copies are currently correct and both are independently tested, so nothing is broken
today. The cost is latent and lands on whoever edits one of them.

## Evidence

`scripts/purge/sweep.py` at `9612d28`:

```
314:    if result.returncode == 1:
316:    if result.returncode != 0:
318:            f"git grep {list(args)!r} failed (exit {result.returncode}): "
448:    if result.returncode == 1:
450:    if result.returncode != 0:
452:            f"git grep -nPoI (identity probe) failed (exit {result.returncode}): "
```

Both are covered by tests, verified by the task-3.2 reviewer in round 3: mutating the
identity probe's copy to `if False:` reds `test_run_identity_probe_sweep_raises_rather_than_swallow_a_real_failure`
as a sole failure, and `test_git_grep_fixed_files_raises_rather_than_swallow_a_real_failure`
covers the helper's copy. So a divergence would be *caught* by the suite — the risk is
that a future edit changes one copy deliberately and the other is never revisited.

Recommended by the task-3.2 reviewer subagent in its round-3 verdict: "Worth a
`.kiro/queue/` note for whoever touches either, not a defect and not blocking."

## How to pick it up

1. Read `scripts/purge/sweep.py` `_git_grep_files` (~line 300) and
   `run_identity_probe_sweep` (~line 430) side by side. The only real difference is the
   git arguments and what is parsed out of stdout.
2. Decide between two fixes. Either extract the exit-code split into a small helper both
   call (`_check_git_grep_exit(result, args)`), leaving each caller to parse its own
   stdout shape — this is the smaller change and does not touch `_git_grep_files`'
   `-l -z` return contract. Or, if that reads worse than the duplication, add a comment
   at each site naming the other by line-independent description, so an editor of one
   finds the other.
3. Run `uv run pytest` with `FITDOCS_FORBIDDEN_STRINGS` exported (see
   `.kiro/specs/encumbered-content-purge/tasks.md` Implementation Notes — unset, token
   checks degrade to a skip and the suite still exits 0). Both existing tests must still
   red under their respective mutations.

Done means: the rule exists once, or each copy names the other, and both mutations still
red.

## Open questions

None. Either fix is acceptable; the choice is a readability judgment.
