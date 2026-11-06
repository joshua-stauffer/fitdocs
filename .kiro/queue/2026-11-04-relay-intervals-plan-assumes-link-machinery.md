---
id: 2026-11-04-relay-intervals-plan-assumes-link-machinery
title: The relay-intervals design and tasks still plan around /go/, robots.txt and the link setting
status: open
importance: medium
importance_why: An implementer following these tasks literally would look for code that is gone, or restore it; nothing else schedules the fix, so it has to happen before /kiro-impl relay-intervals.
effort: S
kind: inconsistency
area: relay-intervals
created: 2026-11-04
surfaced_by: review of the strava-publish Amendment 1 branch
pinned_at: 61c2ece1
resume_command: "/kiro-spec-design relay-intervals [queue: .kiro/queue/2026-11-04-relay-intervals-plan-assumes-link-machinery.md] Remove the plan's references to /go/, robots.txt and the link setting, which strava-publish Amendment 1 removed"
context:
  - .kiro/specs/relay-intervals/design.md
  - .kiro/specs/relay-intervals/tasks.md
  - .kiro/specs/strava-publish/requirements.md
blocked_by: []
---

## What
strava-publish Amendment 1 removed `/go/`, `/robots.txt` and the `relay` link
setting. `policy_sections` and `consent_text` no longer take a link setting. The
`relay-intervals` plan was written before that and still names them as parts of
Strava that stay in place when the shared machinery is lifted.

## Why it matters
Removal only shrinks what stays Strava's, so the plan is stale rather than broken.
A session following task 2.4 literally would still look for that code, or put it
back. The roadmap already plans to rewrite this spec in the Phase 14 extension's
cross-spec review, so fix it there.

## Evidence
- `.kiro/specs/relay-intervals/design.md:100`: "Strava's behaviour, its budget,
  resolver, publisher, webhook and `/go/`".
- `.kiro/specs/relay-intervals/design.md:220`: "resolver, publisher, webhook, `/go/`,
  `robots.txt` and its webhook".
- `.kiro/specs/relay-intervals/design.md:1135-1136`: "`policy_sections(links)` and
  `consent_text(links)` for the configured link setting), `/go/`, `robots.txt`".
- `.kiro/specs/relay-intervals/tasks.md:235`: "Strava's routes keep publish, upload,
  the link redirect, the robots file".

## How to pick it up
1. Read strava-publish's Amendment 1.
2. Remove these references from the `relay-intervals` design and tasks during the
   rewrite. Search for `go/`, `robots` and `link setting`.
3. Add the terms footer link and the acceptance sentence to the plan's connect page,
   since a hosted deployment's terms apply to each platform.
4. Done means the plan describes only code that exists, and its connect page matches
   Strava's.

## Update 2026-11-06
The rewrite this item defers to no longer exists. `.kiro/steering/roadmap.md:4460-4462`
(reverted 2026-11-05) says relay-intervals keeps the lift in its own tasks and "No
cross-spec rewrite is due". Nothing now schedules this fix, so run the resume command
above before `/kiro-impl relay-intervals`, whichever way its gate opens
(`.kiro/specs/relay-intervals/research.md:388`, still pending on this date). Read "the
rewrite" in step 2 as that spec revision. Pinned at a6038449.
