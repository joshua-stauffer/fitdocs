---
id: 2026-11-03-relay-principal-data-export-command
title: Give relay operators a command that shows what the relay holds for one principal
status: open
importance: medium
importance_why: A deployment's contributed policy (the hosted one first) promises access and export on request; today an operator can answer only by querying the database by hand.
effort: M
kind: gap
area: relay-legal-pages, relay-server, relay/src/fitdocs_relay/cli.py
created: 2026-11-03
surfaced_by: /kiro-spec-quick relay-legal-pages (requirements and design)
pinned_at: 50d5d33c
resume_command: "/kiro-spec-requirements relay-server [queue: .kiro/queue/2026-11-03-relay-principal-data-export-command.md] An operator command that prints what the relay holds for one principal"
context:
  - .kiro/specs/relay-legal-pages/requirements.md
  - .kiro/specs/relay-legal-pages/design.md
  - docs/relay.md
  - relay/src/fitdocs_relay/cli.py
  - relay/src/fitdocs_relay/storage/interface.py
blocked_by:
  - relay-legal-pages
---

## What
relay-legal-pages (slim version, 2026-11-03) leaves the access, export and
deletion request process to each deployment: the hosted wrapper contributes a
rights section promising athletes a copy of what the relay holds about them
on request, and the relay docs tell operators to contribute the commitments
their platforms require (Requirement 9.3). The spec deliberately ships no
tooling for answering such requests ("Out of scope: ... an operator command that exports what the relay
holds about one athlete"). The operator commands today are `principal
create|list|delete`, `token mint|list|revoke` and the Strava/key commands
(`docs/relay.md` "Operator commands"); none prints a principal's connections,
publication records, budget counts or wrapper records.

## Why it matters
Each access or export request needs hand-written SQL against
`principals`, `tokens`, `target_connections`, `target_publications`,
`budget_counts` and `records`, on SQLite or PostgreSQL. Done by hand, a
request can easily print a secret (a sealed token or a keyed hash) or miss a
table. Platform developer terms commonly expect these rights; Garmin's
public agreement (FRM-0952 Rev. B §15.4(d)) is one public example.

## Evidence
- `.kiro/specs/relay-legal-pages/requirements.md` Boundary Context, "Out of
  scope": "enforcing anything the policy states, including an operator
  command that exports what the relay holds about one athlete".
- `.kiro/specs/relay-legal-pages/requirements.md` Requirement 7.3: the
  relay ships "no process for access, export or deletion requests"; a
  deployment contributes it (Requirement 8.1).
- `docs/relay.md` "Operator commands" table at 50d5d33c: no per-principal
  data command.

## How to pick it up
1. Read relay-legal-pages' retention text (design.md Supporting References)
   for the list of what the relay holds.
2. Read `storage/interface.py` for read operations per principal. Decide
   whether a new storage read is needed on both backends; if so, the
   conformance suite covers it.
3. Draft `fitdocs-relay principal show ID` (or `export`). It prints
   non-secret facts only (targets connected and when, publication ids and
   match facts, token ids, labels and states), never a token, hash or
   ciphertext. "Done" means a command, its docs row and conformance on both
   backends.

## Open questions
- How does an athlete identify their relay account to an operator without
  sending their relay token? Options: by token id (would fitdocs show it?),
  or the hosted wrapper's registration email.
- Should wrapper records (per-extension namespaces) be included, or left to
  each wrapper?
