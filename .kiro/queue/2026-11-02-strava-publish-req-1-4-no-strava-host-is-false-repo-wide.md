---
id: 2026-11-02-strava-publish-req-1-4-no-strava-host-is-false-repo-wide
title: "strava-publish Req 1.4 (\"the fitdocs source names no Strava host\") is false repo-wide"
status: open
importance: low
importance_why: "A requirement the repo cannot satisfy literally; a future guard test written from it would fail."
effort: S
kind: inconsistency
area: "strava-publish Req 1.4, src/fitdocs/metrics/mean_max_sources.py"
created: 2026-11-02
surfaced_by: "/kiro-validate-impl strava-publish"
pinned_at: 964cc419
resume_command: "/kiro-spec-requirements strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-req-1-4-no-strava-host-is-false-repo-wide.md] Narrow 1.4 to request hosts (or scope the check to the connector modules)"
context:
  - .kiro/specs/strava-publish/requirements.md
  - src/fitdocs/metrics/mean_max_sources.py
  - tests/connectors/test_boundary.py
blocked_by: []
---

## What
`src/fitdocs/metrics/mean_max_sources.py` (analytics-derived, on main) cites a support.strava.com article in a comment/data string. Req 1.4 says the fitdocs source names no Strava host.

## Why it matters
The requirement and a pre-existing file disagree; the connector-scoped checks pass, a repo-wide one would not.

## Evidence
`src/fitdocs/metrics/mean_max_sources.py:23`: `'for Cycling on Strava?" (https://support.strava.com/en-us/articles/'`; `requirements.md:151` (Req 1.4).

## How to pick it up
Amend 1.4 to "no connector sends a request to a Strava host" (or scope to src/fitdocs/connectors).
