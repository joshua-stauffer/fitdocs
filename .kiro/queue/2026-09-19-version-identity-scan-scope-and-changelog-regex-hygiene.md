---
id: 2026-09-19-version-identity-scan-scope-and-changelog-regex-hygiene
title: Version-identity scan excludes .github/, two release-heading regexes are hand-copied, and the CHANGELOG allowlist comment overstates the pin
status: open
importance: low
importance_why: Each is a small drift hazard around the one-literal rule; none is live today.
effort: S
kind: chore
area: distribution, tests/test_version_identity.py, scripts/check_artifacts.py, tests/test_changelog.py
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: widen tests/test_version_identity.py's scan roots to include .github/ (allowlisting release.yml's example comment), share the release-heading regex between scripts/check_artifacts.py and tests/test_changelog.py, correct the CHANGELOG allowlist docstring (whole file is permitted, not only the newest entry), and decide whether Keep-a-Changelog's `[YANKED]` suffix should be accepted"
context:
  - tests/test_version_identity.py
  - scripts/check_artifacts.py
  - tests/test_changelog.py
  - .github/workflows/release.yml
  - CHANGELOG.md
blocked_by: []
---

## What
release.yml carries `v0.1.0` in a comment outside the scan; `_RELEASE_HEADING_RE` exists in two files; tests/test_version_identity.py:~239-243 says only the newest CHANGELOG entry is a permitted copy while the code permits the whole file; `## [0.1.0] - 2026-01-01 [YANKED]` is rejected by both regexes.

## Why it matters
The design says no other literal copy exists anywhere in the repository; the scan's scope makes that true only for the roots it walks.

## Evidence
Implementation Notes 1.1, 1.3; validation reports findings 4 (integration) and 6 (coverage), 2026-09-19.

## How to pick it up
Four small edits, each with a mutation. Done when the design's wording and the scan's scope agree.
