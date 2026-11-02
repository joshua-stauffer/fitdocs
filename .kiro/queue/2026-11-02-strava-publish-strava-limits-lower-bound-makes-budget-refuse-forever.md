---
id: 2026-11-02-strava-publish-strava-limits-lower-bound-makes-budget-refuse-forever
title: "Configured Strava limits accept values that make the budget refuse every upload or link forever"
status: open
importance: low
importance_why: "A misconfigured but accepted limit produces a relay that never publishes, with no startup refusal."
effort: S
kind: bug
area: "relay/src/fitdocs_relay/strava/config.py, relay/src/fitdocs_relay/strava/budget.py, docs/relay.md"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.3 review and validate-impl"
pinned_at: 964cc419
resume_command: "do: raise LIMIT_RANGE's lower bound or document and floor the minimums; add a config test (read .kiro/queue/2026-11-02-strava-publish-strava-limits-lower-bound-makes-budget-refuse-forever.md first)"
context:
  - relay/src/fitdocs_relay/strava/config.py
  - relay/src/fitdocs_relay/strava/budget.py
  - docs/relay.md
  - .kiro/specs/strava-publish/design.md
blocked_by: []
---

## What
`LIMIT_RANGE` accepts 1. An upload reserves `MAX_UPLOAD_POLLS + UPLOAD_FOLLOW_UPS` (8 + 2 = 10) reads, so a read limit below about 20 per 15 minutes (reservation above floor(read_15m/2)) refuses every upload. `for_link` ceilings (`LINK_HEADROOM` 0.2, floor of limit*(1-0.2)) have no `max(1, ...)` floor, so a read limit of 1 or 2 makes every /go/ click "try later". docs/relay.md states no minimum.

## Why it matters
Silent permanent refusal from a config the relay accepts.

## Evidence
- `relay/src/fitdocs_relay/strava/config.py:61`: `LIMIT_RANGE = (1, 1_000_000)`.
- `relay/src/fitdocs_relay/strava/publish.py:68-69`: `MAX_UPLOAD_POLLS = 8`, `UPLOAD_FOLLOW_UPS = 2`.
- `relay/src/fitdocs_relay/strava/budget.py:25-26,85`: `PRINCIPAL_SHARE = 0.5`, `LINK_HEADROOM = 0.2`, `_floor_of(limit, 1 - LINK_HEADROOM)`.
- The arithmetic is the reviewers' (3.3, validate); not exercised by a run.

## How to pick it up
1. Write tests with read limits 1, 2 and 19 showing the refusals.
2. Raise the lower bound (at least the reservation times two) or refuse at startup naming the minimum; document it in docs/relay.md.
