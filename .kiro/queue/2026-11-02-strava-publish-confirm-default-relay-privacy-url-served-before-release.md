---
id: 2026-11-02-strava-publish-confirm-default-relay-privacy-url-served-before-release
title: "Before release, confirm https://api.fitdocs.ai/privacy is served by the default relay"
status: open
importance: medium
importance_why: "docs/connectors.md tells athletes the default relay publishes its policy there; a dead link is a consent-page defect."
effort: S
kind: chore
area: "docs/connectors.md, relay deployment (maintainer-only)"
created: 2026-11-02
surfaced_by: "/kiro-validate-impl strava-publish"
pinned_at: 964cc419
resume_command: "do: maintainer confirms https://api.fitdocs.ai/privacy returns the relay's privacy policy once the default relay has Strava configured, before the release (read .kiro/queue/2026-11-02-strava-publish-confirm-default-relay-privacy-url-served-before-release.md first)"
context:
  - docs/connectors.md
  - .kiro/queue/2026-10-31-strava-publish-site-copy.md
  - relay/LIVE_CHECK_STRAVA.md
blocked_by: [strava-publish release]
---

## What
The privacy page exists only while that relay has Strava configured. Nothing in the repo can verify it; an agent must not make network requests for it. The infrastructure notes live outside this repo.

## Why it matters
Athletes would be sent to a missing policy page during consent.

## Evidence
`docs/connectors.md:849`: `https://api.fitdocs.ai/privacy.` (says the default relay publishes a policy there).

## How to pick it up
1. Maintainer opens the URL after the deploy that configures Strava on the default relay.
2. If it is not served, fix the deploy or reword docs/connectors.md at that line.
3. Close this item with the date checked.
