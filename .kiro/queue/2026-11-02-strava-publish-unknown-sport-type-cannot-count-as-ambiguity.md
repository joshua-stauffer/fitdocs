---
id: 2026-11-02-strava-publish-unknown-sport-type-cannot-count-as-ambiguity
title: "A listed Strava activity with an unknown or missing sport type cannot make a resolution ambiguous"
status: open
importance: high
importance_why: "Can pick the wrong activity (update the wrong page) or upload a duplicate; both change what an athlete sees on Strava."
effort: M
kind: bug
area: "relay/src/fitdocs_relay/strava/resolve.py, strava-publish Req 6.2"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.2 and 3.4 reviews"
pinned_at: 964cc419
resume_command: "/kiro-spec-design strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-unknown-sport-type-cannot-count-as-ambiguity.md] Decide how a start-tolerance hit with an unknown or missing sport type counts in the Resolver"
context:
  - .kiro/specs/strava-publish/requirements.md
  - .kiro/specs/strava-publish/design.md
  - relay/src/fitdocs_relay/strava/resolve.py
blocked_by: []
---

## What
`_facts` drops a candidate with absent or unknown `sport_type` (or both measures absent), so it can never match. Consequences: if the same session also exists under a known type, that one is picked as unique instead of MANY; on upload, a session Strava holds only under a type outside the table resolves not-found and leads to an upload (a duplicate).

## Why it matters
Wrong activity updated or a duplicate activity uploaded for the athlete.

## Evidence
`relay/src/fitdocs_relay/strava/resolve.py:112` `def _facts(...) -> StrictFacts | None:` and `:113` `family = SPORT_FAMILIES.get(candidate.sport_type or "")`; `.kiro/specs/strava-publish/requirements.md:222` (6.2). Behavioural consequences reported by reviewer subagent, unverified by a run.

## How to pick it up
1. Write the two scenarios as failing tests in relay/tests/strava/test_resolve*.py.
2. Decide with the maintainer: a start-tolerance hit with an unknown type counts toward MANY (refuse) - the safe default for Req 6.2.
3. Amend design § Resolver and implement.

## Open questions
Is refusing (MANY) on an unknown-typed near-start activity acceptable when it blocks legitimate publishes after Strava adds a new sport type?

## Update 2026-11-06: raised to high
The default relay now serves Strava with a real athlete, so this code runs against real activities, and a wrong update or duplicate upload lands on an athlete's public account. The behavioural consequences are still reported by reviewers, not reproduced: step 1's failing tests are the first thing to do.
