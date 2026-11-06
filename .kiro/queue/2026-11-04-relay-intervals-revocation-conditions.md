---
id: 2026-11-04-relay-intervals-revocation-conditions
title: The relay-intervals rewrite should decide whether token revocation stays conditional
status: open
importance: low
importance_why: Only matters once the relay route to intervals.icu is built, and that is gated; it costs one maintainer decision, taken in a spec revision before /kiro-impl relay-intervals.
effort: S
kind: inconsistency
area: relay-intervals, relay-server
created: 2026-11-04
surfaced_by: review of the hosted policy pages against the relay specs
pinned_at: 61c2ece1
resume_command: "/kiro-spec-requirements relay-intervals [queue: .kiro/queue/2026-11-04-relay-intervals-revocation-conditions.md] Decide whether revocation is unconditional on disconnect, on refusal and on principal deletion"
context:
  - .kiro/specs/relay-intervals/requirements.md
  - .kiro/specs/relay-server/requirements.md
  - relay/src/fitdocs_relay/storage/postgres.py
blocked_by: []
---

## What
intervals.icu's OAuth rules say to revoke the access token when a user disconnects
or deletes their data. The `relay-intervals` requirements revoke only when the
call budget allows, and do not revoke at all when a principal is deleted.

## Why it matters
The relay would keep to its budget by breaking an instruction from the platform
that approves its OAuth application. The roadmap already plans to rewrite this
spec in the Phase 14 extension's cross-spec review, so this is cheapest to settle
there. Under the maintainer's 2026-11-04 rule, weigh it by what can really happen
on the deployed server at its low volume.

## Evidence
- `.kiro/specs/relay-intervals/requirements.md:276` (Requirement 11.3): "ask
  intervals.icu once to revoke the connection's token when the budget allows".
- `.kiro/specs/relay-intervals/requirements.md:278` (Requirement 11.5): a deleted
  principal's connection is deleted in the same transaction, with no revocation.
- `.kiro/specs/relay-intervals/requirements.md:184` (Requirement 4.6): a refused
  connection's token is handled the same way.
- `relay/src/fitdocs_relay/storage/postgres.py:253`: `delete_principal` is one
  transaction and makes no outbound call.
- The upstream wording, "When a user disconnects Intervals.icu in your app or
  deletes their data on your side, revoke the access token", is as recorded by
  the hosted deployment's policy research. It was not re-checked for this item.

## How to pick it up
1. Read Requirements 4.6, 10.5, 10.6, 11.3 and 11.5 in the `relay-intervals`
   requirements, and confirm the upstream wording on intervals.icu's OAuth page.
2. Take the maintainer's answer to the open question below.
3. Done means the rewritten requirements state the rule. If revocation becomes
   unconditional, `principal delete` must make its outbound call before its
   transaction, which changes `relay-server` too.

## Open questions
Exempt revocation calls from the budget's refusal, or accept the budget-conditional
behaviour at this volume and word the hosted policy page to match? The page
currently promises unconditional revocation for intervals.icu.

## Update 2026-11-06
The rewrite this item defers to no longer exists. `.kiro/steering/roadmap.md:4460-4462`
(reverted 2026-11-05) says relay-intervals keeps the lift in its own tasks and "No
cross-spec rewrite is due". Nothing now schedules this decision, so run the resume
command above before `/kiro-impl relay-intervals`, whichever way its gate opens
(`.kiro/specs/relay-intervals/research.md:388`, still pending on this date). Read "the
rewritten requirements" in step 3 as that spec revision. Pinned at a6038449.
