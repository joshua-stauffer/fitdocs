---
id: 2026-11-01-relay-requirement-wording-vs-rulings
title: 'Three relay-server requirements read differently from the rulings that were implemented'
status: open
importance: low
importance_why: The requirements are the acceptance text; a validator reading them literally will find three apparent failures.
effort: S
kind: spec-work
area: .kiro/specs/relay-server/requirements.md, design.md
created: 2026-11-01
surfaced_by: /kiro-validate-impl relay-server (F-1, F-2, F-3)
pinned_at: 774a883c
resume_command: "/kiro-spec-requirements relay-server [queue: .kiro/queue/2026-11-01-relay-requirement-wording-vs-rulings.md] Amend Req 2.7/9.3/9.4, 3.6 and 10.5 to the ruled behaviour"
context:
  - .kiro/specs/relay-server/requirements.md
  - .kiro/specs/relay-server/design.md
  - relay/tests/test_cli.py
  - relay/src/fitdocs_relay/routes.py
  - docs/relay.md
blocked_by: []
---

## What
Three requirements need wording amended to match the controller rulings.
- F-1: Req 2.7/9.3/9.4 say every operator command refuses a bad environment. `new-pepper` deliberately ignores it (design:1521).
- F-2: Req 3.6 reads as if `serve` is schema-gated; the 5.2 ruling is that serve is not schema-gated and readiness covers it.
- F-3: Req 10.5 says a seam-issued token is "not issued through the seam" for a CLI-minted token; the implementation accepts any token that authenticates as its own token_id and principal_id, so a provider can wrap a CLI-minted token. `docs/relay.md` already says so.

## Why it matters
Validation reports will keep flagging these as defects, and a reader choosing between text and code has no way to tell which is intended.

## Evidence
- `.kiro/specs/relay-server/design.md:1521`: `new-pepper` needs no configuration.
- `relay/tests/test_cli.py::test_new_pepper_ignores_a_broken_environment`.
- `relay/src/fitdocs_relay/routes.py:170-180`: `authenticate` then token_id/principal_id equality.

## How to pick it up
1. Read Req 2.7, 9.3, 9.4, 3.6 and 10.5 in requirements.md.
2. Amend each to state the ruled behaviour (new-pepper exempt; serve not schema-gated; seam token must authenticate as its stated ids).
3. Re-run `/kiro-validate-impl relay-server` on those rows.
