---
id: 2026-11-01-relay-cli-redactor-environ-reads
title: 'The relay CLI''s redactor builds a fake config and reads the environment outside load_config'
status: open
importance: low
importance_why: Type-unsound shortcut plus an unguarded environment read; a new secret variable read directly would not be caught.
effort: S
kind: chore
area: relay/src/fitdocs_relay/cli.py, relay/src/fitdocs_relay/serve.py, relay/tests/test_config.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 5.2 review; /kiro-validate-impl relay-server (G.5-1)
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-cli-redactor-environ-reads.md] Split database_secrets(target) and guard environment reads"
context:
  - relay/src/fitdocs_relay/cli.py
  - relay/src/fitdocs_relay/serve.py
  - relay/tests/test_config.py
blocked_by: []
---

## What
`_environment_redactor` reads the pepper, database URL and password straight from `os.environ` and passes a `SimpleNamespace` through `cast(RelayConfig, ...)` to `database_secrets`, which only works because it reads `.database`. The binding test for the environment table cannot see a new direct read of a non-table name.

## Why it matters
A change to `database_secrets` that reads another config field fails only at runtime in an error path; a new secret read outside `load_config` goes unredacted.

## Evidence
- `relay/src/fitdocs_relay/cli.py:94-110`: the reads and `cast(RelayConfig, SimpleNamespace(database=target))`.
- `relay/src/fitdocs_relay/serve.py:60`: `database_secrets(config: RelayConfig)`.
- `relay/tests/test_config.py:496-540`: the binding tests.

## How to pick it up
1. Split `database_secrets(target)` from the config wrapper and drop the cast.
2. Add a test (AST or grep) that `os.environ` is read in the relay only inside config.py and this one documented function.
3. Done when the cast is gone and the guard fails on a probe read.
