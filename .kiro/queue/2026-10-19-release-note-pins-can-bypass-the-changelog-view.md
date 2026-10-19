---
id: 2026-10-19-release-note-pins-can-bypass-the-changelog-view
title: Nothing stops a release-note pin from reading "## [Unreleased]" directly, so a release cut can break it
status: open
importance: medium
importance_why: A pin that reads [Unreleased] directly fails on the release commit itself; at the 0.2.0 cut it took a CI round trip, and an unguarded one would surface only on the tag's gates job.
effort: S
kind: gap
area: tests/_changelog_view.py, docs/releasing.md, tests/
created: 2026-10-19
surfaced_by: 0.2.0 release cut (CI run 39323298113 on the first cut commit)
pinned_at: 4e172c8
resume_command: "do: add a guard test that fails when any tests/*.py other than tests/_changelog_view.py reads CHANGELOG.md's '## [Unreleased]' section directly instead of through read_unreleased_since/unreleased_since, with a positive control proving the scan sees files; see .kiro/queue/2026-10-19-release-note-pins-can-bypass-the-changelog-view.md"
context:
  - tests/_changelog_view.py
  - tests/test_local_time_docs.py
  - docs/releasing.md
blocked_by: []
---

## What
`docs/releasing.md` step 2 says that release-note pins read the changelog
through `tests/_changelog_view.py`, and so no test needs editing in a release
commit. Nothing enforces this. `tests/test_local_time_docs.py` partitioned on
`"## [Unreleased]\n"` itself. At the 0.2.0 cut its local-time entry moved
under `## [0.2.0]`, and its two pins failed on every CI leg (gates, 3.12,
3.13).

## Why it matters
The cut commit is the revision being released. A pin that breaks there blocks
the release until a test is rewritten, which is exactly what step 2 promises
won't happen. If the cut had been tagged without its own CI run, the
tag-triggered `gates` job would have failed after the tag was pushed.

## Evidence
- CI run 39323298113 (first cut commit, 0fbc0ef): `2 failed` in
  `tests/test_local_time_docs.py::test_release_note_names_the_advance_to_the_current_version`
  and `::test_release_note_states_the_rule_the_action_and_the_renames`.
- Fixed at 8d1307d (read via `read_unreleased_since(..., V0_1_0)`); a mutation
  renaming the entry's opening words reddens both pins, revert is green.
- `grep -rln 'partition("## \[Unreleased\]' tests` now lists none outside
  the helper (at 4e172c8).

## How to pick it up
1. Write a guard in `tests/test_changelog.py` that walks `tests/**/*.py`
   (excluding `_changelog_view.py`) for text reads of `CHANGELOG.md`
   combined with an `[Unreleased]` split, partition or index.
2. Give it a positive control (it scanned more than zero files) and a
   negative fixture showing that a direct read is caught.
3. Done when reverting 8d1307d reddens the guard.
