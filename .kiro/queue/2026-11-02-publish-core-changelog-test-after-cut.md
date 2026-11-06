---
id: 2026-11-02-publish-core-changelog-test-after-cut
title: Two changelog tests fail on the next release cut, against the runbook's promise that no test needs editing
status: open
importance: medium
importance_why: A correct 0.3.0 cut commit goes red in CI and in the tag's gates job, and the fix is a few lines; nothing wrong reaches a user.
effort: XS
kind: test-defect
area: publish-core, tests/publish/test_changelog_entry.py, tests/test_ownership_contract.py, docs/releasing.md
created: 2026-11-02
surfaced_by: /kiro-impl intervals-publish; second test found by a rehearsed cut on 2026-11-06
pinned_at: 35311b53
resume_command: "do: before cutting 0.3.0, delete the two changelog-reading tests named in .kiro/queue/2026-11-02-publish-core-changelog-test-after-cut.md, then rehearse the cut in a scratch worktree and confirm the suite is green"
context:
  - tests/publish/test_changelog_entry.py
  - tests/test_ownership_contract.py
  - tests/_changelog_view.py
  - docs/releasing.md
blocked_by: []
---

## What
`test_entry_is_in_unreleased_not_in_the_0_2_0_section` splits the raw CHANGELOG at the first section after [Unreleased], so after a 0.3.0 cut it treats 0.3.0 as 'released' and fails on a correctly placed entry.

## Why it matters
Cutting 0.3.0 (or any release) will red CI on a correct changelog.

## Evidence
tests/publish/test_changelog_entry.py ~50-54; simulated cut (add '## [0.3.0] - date' under [Unreleased]) reds it while tests/connectors/test_intervals_changelog.py passes (it reads through `read_unreleased_since(_, V0_2_0)`).

## Update 2026-11-06: a rehearsed cut found a second test
At 35311b53, in a detached scratch worktree, the cut's seven-file edit was applied (`## [0.3.0] - 2026-11-06` under `## [Unreleased]`; the version in `pyproject.toml`, the four packaged `SKILL.md` files and `uv.lock`), and `uv run pytest -n auto` printed:

```
FAILED tests/publish/test_changelog_entry.py::test_entry_is_in_unreleased_not_in_the_0_2_0_section
FAILED tests/test_ownership_contract.py::test_changelog_names_contract_version_nineteen_and_its_action
2 failed, 32661 passed, 47 skipped in 76.05s
```

- `tests/test_ownership_contract.py:740` reads the raw changelog with `text.split("## [Unreleased]", 1)[1].split(" ## [", 1)[0]`, which is empty straight after a cut. It was not known before this rehearsal.
- `docs/releasing.md` step 2 says "No test needs editing in the release commit", which is false for both.
- `2026-10-19-release-note-pins-can-bypass-the-changelog-view` recorded no direct readers left, but its grep looked for `partition(` only and this test uses `split(`.
- The rest of the rehearsal was clean: `tests/sitebuild` with the docs group (737 passed), `ruff`, and step 3's `scripts.check_artifacts --no-artifacts --tag v0.3.0`. The rehearsal ran on Python 3.11 only, with the forbidden-strings gate unarmed and without `mypy`.

## How to pick it up
Both tests read `CHANGELOG.md`. Under the maintainer's 2026-11-03 rule that only code is under test, a doc-binding test a change would turn red is deleted by default, not updated, so delete them. Repointing them through `read_unreleased_since(..., V0_2_0)`, as `tests/connectors/test_intervals_changelog.py` does, is the alternative if the maintainer wants them kept.

Done when a rehearsed cut, as above, leaves the full suite green. Do this on a branch before the release commit, so the cut commit needs no test edits.

## Update 2026-11-06: fixed on chore/pre-cut-fixes
Both tests are deleted (commit "test: delete two changelog tests that fail on a correct release cut"). A rehearsed cut on that branch printed `32667 passed, 47 skipped` with no failures, on Python 3.11. Left open for the maintainer to close.
