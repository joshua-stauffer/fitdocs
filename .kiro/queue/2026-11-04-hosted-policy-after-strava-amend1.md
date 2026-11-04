---
id: 2026-11-04-hosted-policy-after-strava-amend1
title: Re-read the hosted policy pages against strava-publish Amendment 1 at the Strava go-live
status: open
importance: low
importance_why: Required by the roadmap's hosted-policy constraint; the pages were already updated, so this only confirms them against the deployed build.
effort: S
kind: chore
area: strava-publish, relay
created: 2026-11-04
surfaced_by: review of the strava-publish Amendment 1 branch
pinned_at: 61c2ece1
resume_command: "do: at the Strava go-live of the hosted deployment, re-read its policy pages against the relay build being deployed, following that deployment's go-live list (read .kiro/queue/2026-11-04-hosted-policy-after-strava-amend1.md first)"
context:
  - .kiro/specs/strava-publish/requirements.md
  - relay/src/fitdocs_relay/strava/policy.py
  - docs/relay.md
blocked_by: []
---

## What
Amendment 1 changes what the relay stores, returns and deletes:
- it no longer serves `/go/` or `/robots.txt`, and has no link setting;
- it keeps no publication record, so it keeps no workout facts;
- it adds an optional `FITDOCS_RELAY_TERMS_URL`, a footer link and one acceptance
  sentence on the connect page;
- `fitdocs disconnect` says that the relay deleted the connection.

The roadmap's Phase 14 extension requires a change like this to record an item for
the hosted deployment's policy pages, because their text is not in this repository.

## Why it matters
Nothing here can catch drift between the relay and the hosted pages. The hosted
pages were rewritten on 2026-11-04 to match this amendment before it landed, so
they describe the build that carries it. If a deployment shipped an earlier build
after Strava went live, the pages would be wrong about it.

## Evidence
- `.kiro/steering/roadmap.md`, "The hosted policy pages describe public code".
- `.kiro/specs/strava-publish/requirements.md`, "Amendment 1 (2026-11-04)".
- The behaviour landed in 7d37e032 (`/go/` and the link setting), fb5aacce (publication
  records) and af26ab4d (terms address and disconnect wording).

## How to pick it up
1. Read the amendment and the deployed build's commit.
2. Follow the hosted deployment's go-live list. It already names this amendment as
   a precondition for Strava, and asks for `FITDOCS_RELAY_TERMS_URL` to be set.
3. Done means each sentence about Strava on the pages matches the deployed relay.
