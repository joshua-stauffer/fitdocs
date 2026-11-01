---
id: 2026-11-01-relay-migrate-check-creates-sqlite-file
title: '`migrate --check` creates an empty SQLite file when the configured path does not exist'
status: open
importance: low
importance_why: Conflicts with the "changes nothing" reading of Req 8.6/3.6 for a check command.
effort: S
kind: inconsistency
area: relay/src/fitdocs_relay/storage/sqlite.py, relay/src/fitdocs_relay/cli.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 5.2 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-migrate-check-creates-sqlite-file.md] Decide whether check-only commands may create the database file"
context:
  - relay/src/fitdocs_relay/storage/sqlite.py
  - .kiro/specs/relay-server/design.md
  - .kiro/specs/relay-server/requirements.md
  - relay/tests/test_cli.py
blocked_by: []
---

## What
Every schema-gated command, including `migrate --check`, constructs the SQLite backend, whose `__init__` creates the file. The design sanctions the creation, but a check that leaves a 4096-byte WAL database behind reads as a change.

## Why it matters
A typo in the configured path produces a stray database and a check that reports "pending" for an empty schema rather than "no such database".

## Evidence
- `rm a.db*; fitdocs-relay migrate --check` exits 3 and leaves `a.db` (observed in 5.2).
- `relay/src/fitdocs_relay/storage/sqlite.py:103` calls `self._create_file()`; `:410` defines it; `design.md:1257` sanctions creation.

## How to pick it up
1. Decide: add a read-only open mode for check-only commands, or amend Req 8.6/3.6 and the design to say creation is intended.
2. Implement or amend accordingly, with a test that asserts the file's existence after `--check`.
