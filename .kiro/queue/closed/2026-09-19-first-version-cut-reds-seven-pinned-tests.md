---
id: 2026-09-19-first-version-cut-reds-seven-pinned-tests
title: Seven tests pin the pre-release state and go red in the release commit that cuts the first version
status: done
importance: high
importance_why: Every one runs in the `gates` job on the tagged revision; the first release stops at step 1 unless they change in the same commit.
effort: S
kind: chore
area: distribution, tests/test_changelog.py, tests/test_release_artifacts.py, tests/test_release_workflow.py, tests/test_version_identity.py
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: in the first-release commit, flip the seven tests named in docs/releasing.md step 2 to the released state (a `## [X.Y.Z] - date` heading exists; the pairwise version gate reports zero violations) and update tests/test_version_identity.py's docs/plugins.md allowlist; run uv run pytest -q"
context:
  - docs/releasing.md
  - tests/test_changelog.py
  - tests/test_release_artifacts.py
  - tests/test_release_workflow.py
  - tests/test_version_identity.py
  - docs/plugins.md
blocked_by: []
---

## What
docs/releasing.md step 2 lists them: two in tests/test_changelog.py (no released heading yet; Added entries live under Unreleased), two in tests/test_release_artifacts.py and two in tests/test_release_workflow.py (the version gate reports exactly today's no-entry violation), plus tests/test_version_identity.py's count-exact allowlist for the `version = "0.1.0"` example in docs/plugins.md, which collides with the released literal while the manifest is 0.1.0 and breaks the moment it is not.

## Why it matters
A maintainer following the runbook on a fresh tag gets a red `gates` job with no code defect behind it. The docs/plugins.md collision is the sharper edge: the example snippet is a plugin author's illustration and should not track the release version at all.

## Evidence
tests/test_releasing_docs.py::test_step2_before_first_release_note_names_the_pinned_tests_and_allowlist pins the list (widened to all seven at b29bde8); tests/test_version_identity.py:~250 count-exact allowlist; Implementation Notes 2.4, 3.2, 5.6 in .kiro/specs/distribution/tasks.md.

## How to pick it up
Read docs/releasing.md step 2, then each named test. Consider changing the docs/plugins.md example to a version that can never collide (e.g. `9.9.9`) now, ahead of the release, so the allowlist entry can be deleted. Done when the release commit's `uv run pytest -q` is green with a released heading in CHANGELOG.md.

## Resolution (2026-10-18)

The remaining half is fixed on main at 65aac2c (chore/q-release-hygiene; review APPROVED). docs/plugins.md's
example plugin version is a placeholder (`0.0.1`, pinned to stay below the manifest version) so the
version scan's allowlist is empty. Going further, the 29 tests (not 4) that pinned entries under
`## [Unreleased]` now read through tests/_changelog_view.unreleased_since(text, V0_1_0), so the 0.2.0
release commit (version bump + `## [0.2.0]` heading) flips no tests and neither does the first commit
after it; an entry misplaced into 0.1.0 still fails its pin. Verified by a release-cut simulation on
the merged tree. docs/releasing.md step 2 now also tells the operator to run `uv lock` and commit
uv.lock (the lock records the project version).
