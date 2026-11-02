---
id: 2026-11-02-strava-publish-research-record-strava-field-names-and-sport-list
title: "research.md records no source for Strava field names, the sport-type list, or the comma-delimited callback scope"
status: open
importance: medium
importance_why: "The sport-type table behind SPORT_FAMILIES was written from memory; a missing type silently never matches, and nothing says what the live check must confirm."
effort: S
kind: research
area: ".kiro/specs/strava-publish/research.md, relay/LIVE_CHECK_STRAVA.md, relay/src/fitdocs_relay/strava/resolve.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.2, 3.4, 3.9 reviews and validate-impl"
pinned_at: 964cc419
resume_command: "do: record dated sources in research.md for the Strava fields, the 50-type sport list and the callback scope delimiter, and add each to the maintainer live check (read .kiro/queue/2026-11-02-strava-publish-research-record-strava-field-names-and-sport-list.md first)"
context:
  - .kiro/specs/strava-publish/research.md
  - relay/LIVE_CHECK_STRAVA.md
  - relay/src/fitdocs_relay/strava/resolve.py
  - relay/src/fitdocs_relay/strava/connect.py
blocked_by: []
---

## What
The adapter relies on: `start_date` vs `start_date_local`, `sport_type`, `elapsed_time`, `distance`, `/push_subscriptions`, `callback_url`, the sport-type list (`SPORT_FAMILIES`, about 50 types), and a comma-delimited callback `scope` (`connect.py` splits on commas; a test pins a space-delimited value as a refusal). None has a source or date in research.md.

## Why it matters
Strava adds types and changes fields; without a recorded source the next maintainer cannot tell a Strava change from a bug.

## Evidence
- `relay/src/fitdocs_relay/strava/resolve.py:98` `SPORT_FAMILIES = MappingProxyType(_FAMILIES)`.
- research.md contents not re-grepped in this run for each name; reviewers (3.2, 3.4, 3.9, validate) report none are recorded.

## How to pick it up
1. `grep -n -E 'sport_type|start_date|push_subscriptions|scope' .kiro/specs/strava-publish/research.md`.
2. Add a sourced, dated entry for each, citing Strava's public API reference.
3. Add a line per item to relay/LIVE_CHECK_STRAVA.md (maintainer-run; no live calls from an agent).
