---
id: 2026-11-02-strava-publish-relay-changelog-required-optional-split-unpinned
title: "The relay changelog's required vs optional variable split is not pinned by any test"
status: open
importance: low
importance_why: "FITDOCS_RELAY_PUBLIC_URL could move to Optional with the suite green."
effort: S
kind: chore
area: "relay/CHANGELOG.md, tests/connectors/test_strava_changelog.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 7.5 review"
pinned_at: 964cc419
resume_command: "do: add a test that pins which variables the changelog lists as required and which as optional (read .kiro/queue/2026-11-02-strava-publish-relay-changelog-required-optional-split-unpinned.md first)"
context:
  - relay/CHANGELOG.md
  - tests/connectors/test_strava_changelog.py
  - relay/src/fitdocs_relay/config.py
blocked_by: []
---

## What
The changelog lists the Strava variables as required or optional; no test checks the split against the config module's actual requirements.

## Why it matters
A wrong deployment instruction could pass review.

## Evidence
`relay/CHANGELOG.md:20` lists `FITDOCS_RELAY_PUBLIC_URL`; claim that no test pins the split is the reviewer's (7.5), not re-verified.

## How to pick it up
Derive the required set from config.py and assert the changelog's Required list equals it.
