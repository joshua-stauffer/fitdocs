---
id: 2026-11-02-strava-publish-terms-first-policy-statement-names-one-third-party-connector
title: "docs/connectors.md \"The terms-first policy\" still says intervals.icu is the one third-party service connector fitdocs ships"
status: open
importance: medium
importance_why: "With the Strava (relay-only) connector shipping, the policy sentence is either false or needs a deliberate wording; it is a maintainer call (strava-publish R13.2)."
effort: S
kind: docs
area: "docs/connectors.md, strava-publish Req 13.2"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 7.1 review"
pinned_at: 964cc419
resume_command: "do: maintainer decides the wording of the terms-first policy paragraph in docs/connectors.md now that a relay-only Strava connector ships, then edit it (read .kiro/queue/2026-11-02-strava-publish-terms-first-policy-statement-names-one-third-party-connector.md first)"
context:
  - docs/connectors.md
  - .kiro/specs/strava-publish/requirements.md
  - .kiro/specs/strava-publish/design.md
blocked_by: []
---

## What
The section states that the one third-party service connector fitdocs ships is the intervals.icu one. The Strava connector reaches only the relay, never Strava directly, so the statement may stay true in a narrow sense; the reviewer left the call to the maintainer.

## Why it matters
A policy statement in public docs that can mislead about which third parties fitdocs talks to.

## Evidence
`docs/connectors.md:632` `## The terms-first policy`; `:636` "third-party service connector fitdocs ships is the [intervals.icu](#intervalsicu)".

## How to pick it up
1. Read the paragraph at docs/connectors.md:632-640 and Req 13.2.
2. Maintainer chooses: keep with a clarifying clause (Strava is reached only through a relay you or the default operator runs) or rewrite.
3. Update any docs test that pins the sentence.

## Open questions
Is the relay-mediated Strava connector a "third-party service connector" under the terms-first policy?
