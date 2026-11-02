---
id: 2026-11-02-strava-publish-relay-changelog-unreleased-vs-0-1-0
title: "Decide at the relay release cut whether the Strava target folds into relay 0.1.0 or ships later"
status: open
importance: low
importance_why: "relay/CHANGELOG.md has two headings; cutting without a decision ships a wrong version label."
effort: S
kind: chore
area: "relay/CHANGELOG.md, relay/pyproject.toml"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 7.5 review"
pinned_at: 964cc419
resume_command: "do: at the relay release cut, fold `## Unreleased` into `## 0.1.0 (unreleased)` or choose a new version, then fix tests/connectors/test_strava_changelog.py (read .kiro/queue/2026-11-02-strava-publish-relay-changelog-unreleased-vs-0-1-0.md first)"
context:
  - relay/CHANGELOG.md
  - tests/connectors/test_strava_changelog.py
  - relay/pyproject.toml
blocked_by: []
---

## What
The changelog now has `## Unreleased` (the Strava target) above `## 0.1.0 (unreleased)`.

## Why it matters
Release-cut bookkeeping; a missed fold ships a changelog that disagrees with the version.

## Evidence
`relay/CHANGELOG.md:6` `## Unreleased`; `:44` `## 0.1.0 (unreleased)`.

## How to pick it up
At the cut, decide with the maintainer, edit the headings and run the changelog tests.
