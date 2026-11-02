---
id: 2026-11-01-relay-design-silent-behaviours
title: 'relay-server design is silent on five behaviours the implementation had to choose'
status: open
importance: low
importance_why: Each is a decided behaviour with no written statement; a later change can reverse one without a test or a spec line objecting.
effort: S
kind: docs
area: .kiro/specs/relay-server/design.md, relay/src/fitdocs_relay
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 3.1, 4.3, 6.2 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-design-silent-behaviours.md] Write the five unstated behaviours into the design"
context:
  - .kiro/specs/relay-server/design.md
  - relay/src/fitdocs_relay/identity.py
  - relay/src/fitdocs_relay/answers.py
  - relay/src/fitdocs_relay/cli.py
blocked_by: []
---

## What
Five behaviours need a sentence in design.md.
1. The envelope data-contract table does not state the data for revoke `ok`, `registration-pending` and `registration-slow-down`; the fitdocs client requires `{}`.
2. `authenticate` compares the verifier before checking revocation, so a revoked token with a wrong secret answers `token-unknown`, not `token-revoked`. The controller ruled compare-first.
3. A repeated `Authorization` header: the relay takes the first value.
4. `TokenService.mint(principal_id=<existing>, principal_label=...)` silently drops the label. The CLI refuses the combination; the service does not.
5. (Pairs with 2.) A reader of the identity section cannot tell which of the two orders applies.

## Why it matters
Behaviour that exists only in code is re-decided by the next editor. The first item is a client/server contract: a server returning data on those answers would break the client.

## Evidence
- `design.md:1776` (revoke row) and `:1778` (poll row): no data column entry for these answers.
- `design.md:1319-1327`: the authenticate outcomes list has no ordering statement.
- `relay/src/fitdocs_relay/answers.py:93`: `request.headers.get("authorization")` (first value).
- `relay/src/fitdocs_relay/identity.py:75-90`: `principal_label` is only read on the new-principal branch; `relay/src/fitdocs_relay/cli.py:384-390` refuses it for the CLI.

## How to pick it up
1. Add one sentence per behaviour to design.md at the cited places.
2. For item 4, either state that the service ignores the label for an existing principal, or make `TokenService.mint` refuse it and add a test.
3. Done when each of the five behaviours is stated in the design.
