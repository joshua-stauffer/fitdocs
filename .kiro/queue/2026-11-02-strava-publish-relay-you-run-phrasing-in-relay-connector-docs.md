---
id: 2026-11-02-strava-publish-relay-you-run-phrasing-in-relay-connector-docs
title: "docs/connectors.md describes the relay as one \"you run\" in places where the default relay may be the one in use"
status: open
importance: low
importance_why: "Pre-existing wording; reads as if every athlete operates their own relay."
effort: S
kind: docs
area: "docs/connectors.md"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 7.1 review"
pinned_at: 964cc419
resume_command: "do: review who-runs phrasing in the relay connector section of docs/connectors.md and reword where the operator may be someone else (read .kiro/queue/2026-11-02-strava-publish-relay-you-run-phrasing-in-relay-connector-docs.md first)"
context:
  - docs/connectors.md
blocked_by: []
---

## What
The relay connector section uses "a relay you run" phrasing (reviewer cites ~635 and ~692).

## Why it matters
Minor accuracy of public docs.

## Evidence
`docs/connectors.md:695`: "which is for testing a relay you run" (found at HEAD; the ~635 occurrence did not match this grep).

## How to pick it up
Read both sections and reword in plain language; no behaviour change.
