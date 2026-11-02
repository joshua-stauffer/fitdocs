---
id: 2026-11-02-publish-core-changelog-test-after-cut
title: publish-core's changelog test fails after the next release cut
status: open
importance: low
importance_why: The first release after 0.2.0 will red a correct changelog.
effort: XS
kind: test-defect
area: publish-core, tests/publish/test_changelog_entry.py
created: 2026-11-02
surfaced_by: /kiro-impl intervals-publish
pinned_at: 978c74fa
resume_command: "/kiro-impl publish-core [queue: .kiro/queue/2026-11-02-publish-core-changelog-test-after-cut.md] Read the not-in-0.2.0 check through the changelog view"
context:
  - tests/publish/test_changelog_entry.py
  - tests/_changelog_view.py
  - tests/query/test_changelog_entry.py
blocked_by: []
---

## What
`test_entry_is_in_unreleased_not_in_the_0_2_0_section` splits the raw CHANGELOG at the first section after [Unreleased], so after a 0.3.0 cut it treats 0.3.0 as 'released' and fails on a correctly placed entry.

## Why it matters
Cutting 0.3.0 (or any release) will red CI on a correct changelog.

## Evidence
tests/publish/test_changelog_entry.py ~50-54; simulated cut (add '## [0.3.0] - date' under [Unreleased]) reds it while tests/connectors/test_intervals_changelog.py passes (it reads through `read_unreleased_since(_, V0_2_0)`).

## How to pick it up
Build `released` from `read_unreleased_since(_CHANGELOG, V0_2_0)` as tests/connectors/test_intervals_changelog.py does; re-run with a simulated cut.
