---
id: 2026-08-18-reflog-row-literal-emptiness-does-not-hold-post-swap
title: check_reflog_and_unreachable_gone's literal-emptiness reflog contract does not hold against a real run_replace swap
status: done
importance: medium
importance_why: Major 8 will run verify-local's reflog row against the real post-swap repository; as shipped, that row's reflog half reds on a CORRECT replacement, which is exactly the false-red shape task 7.4 already had to remove once for the porcelain row.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/verify.py, scripts/purge/replace.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge 7.7 (real-runner rehearsal)
pinned_at: aeabf8e
resume_command: "do: before Major 8 runs verify-local for real, decide whether run_replace should clear the post-swap reflog (e.g. git reflog expire --expire=now --all, or core.logAllRefUpdates=false before the clone/rename) or whether check_reflog_and_unreachable_gone's reflog half should be re-scoped the same way task 7.4 re-scoped the porcelain row"
context:
  - scripts/purge/verify.py
  - scripts/purge/replace.py
  - tests/purge/test_replace_rehearsal.py
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`scripts/purge/verify.py::check_reflog_and_unreachable_gone` requires
`git reflog show --all` to report **nothing** (`passed = not reflog and not
fsck`). Measured against a real `run_replace` swap driven by a real command
runner (task 7.7's rehearsal, `tests/purge/test_replace_rehearsal.py`), with
no rehearsal-only shortcut and no extra git config: the real `git clone`
`run_replace` issues, followed by the driver's own `git branch -m` rename,
leaves the post-swap repository's reflog with **two entries per ref**
(`clone: from <source>`, `Branch: renamed refs/heads/<temp> to refs/heads/
main`) for both `HEAD` and `refs/heads/main`. Neither `run_replace` nor any
function it calls (`adopt.move_clone`, `adopt.assert_carry_over`, the
pre-swap rows) clears them. Every entry resolves to the same commit -- the
forged root -- so Req 7.3's actual text ("reflogs ... shall reference no
pre-replacement commit") holds, and design.md `#### HistoryReplacement`'s
"the single-entry reflog references only the root" is also arguably true in
spirit, but `check_reflog_and_unreachable_gone`'s literal `not reflog`
contract does not hold.

This is the same species of gap task 7.4 already closed once for
`check_working_tree_coincides` (a bare porcelain row that is a guaranteed
false red against a correct swap because of the untracked root `agent-log`
symlink) -- except this time it was never flagged before implementation,
because task 7.7 is the first task to drive `run_replace` through a REAL
command runner rather than a recording stand-in.

## Why it matters

`scripts/purge/verify.py::verify_local` (still an unwired stub) is meant to
call `check_reflog_and_unreachable_gone` against the real post-swap
repository as part of Major 8's acceptance procedure. As shipped, this row
will red on Major 8's first real, correct run -- an operator staring at a
one-shot, largely-irreversible operation seeing a verification row fail is
exactly the "guaranteed swap-back trigger on a correct replacement" task
7.4's own docstring warns about, just for the reflog row instead of the
porcelain row.

## Evidence

Measured at `aeabf8e` via `tests/purge/test_replace_rehearsal.py`'s real-runner
rehearsal (task 7.7): after a successful `run_replace` swap,
`git -C <repo_root> reflog show --all` reports:

```
<root-sha> refs/heads/main@{0}: Branch: renamed refs/heads/purge-replacement-root to refs/heads/main
<root-sha> refs/heads/main@{1}: clone: from <scratch-source>
<root-sha> HEAD@{0}: Branch: renamed refs/heads/purge-replacement-root to refs/heads/main
<root-sha> HEAD@{2}: clone: from <scratch-source>
```

Every line resolves (via `git rev-parse <short-sha>`) to the single reachable
root commit -- confirmed directly in the rehearsal's own
`_assert_reflog_references_only` helper, which at this `aeabf8e` snapshot
asserted this literal property by resolving each `git reflog show --all`
line via `git rev-parse`, instead of calling `check_reflog_and_unreachable_gone`
and treating its `.passed` as the pinning assertion for the reflog half. (As
of the task 7.7 remediation round the helper no longer parses `reflog show`
output at all -- see step 3 below.) The `fsck` half of the same row function
(`git fsck --unreachable --dangling`) IS empty and unaffected by this gap.

## How to pick it up

1. Re-read `scripts/purge/verify.py::check_reflog_and_unreachable_gone`'s
   docstring and `design.md` `#### HistoryReplacement`'s "the single-entry
   reflog references only the root" sentence side by side -- decide whether
   the design intends the driver to clear the reflog (a small, justified
   `run_replace` addition -- e.g. `git reflog expire --expire=now --all` on
   the scratch clone before the swap, or `core.logAllRefUpdates=false`
   supplied in the clone/rename environment) or whether the row itself
   should be re-scoped to "references no pre-replacement commit" the same
   way task 7.4 re-scoped the porcelain row to tracked-files-only.
2. Whichever direction is chosen, update BOTH `design.md`'s prose and
   `scripts/purge/verify.py`'s row (or `scripts/purge/replace.py`'s driver)
   together, the same declared-correction pattern task 7.4 used -- do not
   leave the mismatch for Major 8 to discover live.
3. `tests/purge/test_replace_rehearsal.py::_assert_reflog_references_only`
   already implements and pins the literal Req 7.3 property against a real
   swap -- as of the task 7.7 remediation round it reads every file under
   `.git/logs/**` directly rather than parsing `git reflog show --all`
   output, because `reflog show --all` measurably (real git 2.54.0) omits
   any entry whose object is absent from the object database and still
   exits 0. Reuse that file-reading approach (or fold it into
   `check_reflog_and_unreachable_gone`); do NOT reuse or fold in a
   `reflog show`-based form -- `reflog show` is not a sound basis for the
   row, since it would install the exact blind spot above into the
   verification Major 8 runs during the one-shot irreversible operation.

## Open questions

Whether clearing the reflog belongs in `run_replace` (a production change)
or the row's contract should simply be loosened -- a maintainer call, not a
mechanical one; the design's own prose does not currently resolve it either
way it is read literally.

## Resolution

Maintainer approved the second direction (row re-scoped, `run_replace`
unchanged, no reflog clearing added to the driver). `check_reflog_and_
unreachable_gone` now takes `(repo, allowed_commit)` and reads every file
under `.git/logs/**` directly, following `_assert_reflog_references_only`'s
approach (step 3 above) with the null-id discard, vacuous-walk guard and a
40-/64-hex id pattern. `design.md`'s `#### ReplacementVerification` table row
and its "the reflog references only the root" prose (`#### HistoryReplacement`
step 7's neighbouring paragraph) are both amended in place as declared
corrections in the same change. `scripts/purge/replace.py` is untouched, per
this item's own resolution direction. See `tests/purge/test_verify.py`'s
`check_reflog_and_unreachable_gone` section for the new fixtures, including
one pinning the exact absent-object-id defect this item names.
