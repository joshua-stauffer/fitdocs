---
id: 2026-08-19-task-7-7-rehearsal-still-duplicates-the-now-corrected-reflog-row
title: tests/purge/test_replace_rehearsal.py's _assert_reflog_references_only duplicates check_reflog_and_unreachable_gone's reflog half, which no longer disagrees with it
status: open
importance: low
importance_why: A duplicated implementation of the same Req 7.3 property is a maintenance-drift risk (the two id-scan patterns already diverged in width -- see the sibling queue item below), not a correctness gap today; both currently agree on every fixture measured.
effort: S
kind: inconsistency
area: encumbered-content-purge, tests/purge/test_replace_rehearsal.py, scripts/purge/verify.py
created: 2026-08-19
surfaced_by: /kiro-impl encumbered-content-purge (task 7.7 remediation, an independent review's rejection of the check_reflog_and_unreachable_gone defect fix)
pinned_at: c3d2201
resume_command: "do: decide whether tests/purge/test_replace_rehearsal.py should call scripts.purge.verify.check_reflog_and_unreachable_gone directly (dropping _assert_reflog_references_only) now that the task 7.7 remediation's declared correction makes that row pass the real run_replace-produced state -- reflog half only; the fsck half is a separate, already-duplicated command shape in the same module and would need its own decision"
context:
  - tests/purge/test_replace_rehearsal.py
  - scripts/purge/verify.py
  - tests/purge/test_verify.py
  - .kiro/queue/2026-08-19-reflog-id-scan-is-sha1-only-and-misses-the-common-dir.md
blocked_by: []
---

## What

`tests/purge/test_replace_rehearsal.py::_assert_reflog_references_only`
implements the same property as
`scripts/purge/verify.py::check_reflog_and_unreachable_gone`'s reflog half
(read every file under `.git/logs/**`, assert no hex object id other than
the allowed commit appears, discard only the all-zeros placeholder) as an
independent, hand-written copy rather than a call to the production row
function. When this module's docstring was written, that was necessary:
`check_reflog_and_unreachable_gone` demanded `git reflog show --all` report
literal emptiness, which a real `run_replace` swap's `clone: from
<source>`/`Branch: renamed ...` reflog entries genuinely violate.

The task 7.7 remediation's declared correction (the defect fix this queue
item's own remediation closed out) removed that literal-emptiness demand. Measured: the
production row now PASSES the exact driver-produced state this rehearsal
builds. The two implementations currently agree on every fixture in both
modules, but they are still two separate copies of one Req 7.3 property,
and the sibling queue item
`2026-08-19-reflog-id-scan-is-sha1-only-and-misses-the-common-dir.md`
already recorded that their id-scan regexes have diverged in width (this
file's copy is still 40-hex-only; the production copy now also matches
64-hex). A second divergence in the SAME two copies, on the SAME night, is
the kind of drift this item exists to flag before a third one lands
unnoticed.

## Why it matters

Every future change to the reflog property's semantics (e.g. a further
correction to what counts as an allowed id, or the common-dir gap tracked in
the sibling item) has to be applied twice, in two files, by whoever remembers
both copies exist. The regex-width divergence already shows that does not
reliably happen.

## Evidence

- `scripts/purge/verify.py::check_reflog_and_unreachable_gone`'s current
  reflog half (the task 7.7 remediation's declared correction, module
  docstring there) and
  `tests/purge/test_replace_rehearsal.py::_assert_reflog_references_only`
  (module docstring there, corrected in this same change) now describe an
  identical property in different words.
- `tests/purge/test_replace_rehearsal.py::test_run_replace_rehearses_forge_
  clone_swap_and_rollback` calls `_assert_reflog_references_only`, never
  `check_reflog_and_unreachable_gone` -- which that module does not import at
  all, though it does import and use three sibling rows
  (`check_exactly_one_commit_reachable`, `check_tree_identity`,
  `check_working_tree_coincides`).
- `.kiro/queue/2026-08-19-reflog-id-scan-is-sha1-only-and-misses-the-common-
  dir.md` -- the id-pattern width already diverged between these same two
  copies.

## A second, unrecorded divergence (added 2026-08-19, final review)

The two copies of the Req 7.3 id scan have diverged in **two** ways, not one.
Besides the regex width recorded in the sibling item, the production row reads
its log files with `errors="surrogateescape"` -- pinned by
`tests/purge/test_verify.py::test_check_reflog_and_unreachable_gone_does_not_
crash_on_non_utf8_committer_bytes` -- while
`tests/purge/test_replace_rehearsal.py::_assert_reflog_references_only` still
uses a bare `read_text()`. So the rehearsal helper would raise
`UnicodeDecodeError` on exactly the bytes the row now survives, and a reflog
line carries an arbitrary-bytes committer name.

This makes the rehearsal module docstring's "equivalent on sha1" strictly true
only for valid-UTF-8 content. Whoever resolves the duplication resolves this
with it; whoever instead keeps the two copies owes this second difference a
mention alongside the width one.

## How to pick it up

Decide whether `test_replace_rehearsal.py` should drop
`_assert_reflog_references_only` and call
`check_reflog_and_unreachable_gone(root, new_head)` directly for the reflog
half, asserting `.passed`. If yes: the `fsck` half is currently a
duplicated command shape too (module docstring: "the same command shape ...
is re-issued directly below, which is a duplicated command shape, not
function reuse") -- decide both halves together or explain why they diverge.
If no: say so in the module docstring with the reason (this item's own
existence is not, by itself, a reason to keep the duplicate -- e.g. "the
rehearsal must not depend on `ReplacementVerification`'s row functions
changing out from under it silently" would be a real reason; "it works
today" is not).

## Open questions

Whether task 7.6 (CLI wiring, `verify_local`) ends up calling
`check_reflog_and_unreachable_gone` in a context close enough to this
rehearsal's own scratch-repo setup that the duplication becomes trivially
removable then, rather than now.
