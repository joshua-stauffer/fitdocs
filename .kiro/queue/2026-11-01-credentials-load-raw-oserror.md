---
id: 2026-11-01-credentials-load-raw-oserror
title: "CredentialStore.load lets a raw OSError from path.stat() escape unwrapped"
status: open
importance: low
importance_why: Needs an unusual filesystem state (a non-directory parent, bad permissions), but the result is a traceback past documented exception handling.
effort: S
kind: bug
area: connectors, src/fitdocs/connectors/credentials.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: wrap OSError from path.stat() in CredentialStore.load as CredentialStoreError and test NotADirectoryError and PermissionError [queue: .kiro/queue/2026-11-01-credentials-load-raw-oserror.md]"
context:
  - src/fitdocs/connectors/credentials.py
  - src/fitdocs/connectors/pull.py
blocked_by: []
---

## What
`CredentialStore.load` lets a raw `OSError` (`NotADirectoryError`,
`PermissionError`) from `path.stat()` escape. It passes
`resolve_credentials`' documented exceptions and pull's
`(ConnectorError, CredentialStoreError)` catch.

## Why it matters
The user sees a traceback instead of a fitdocs message.

## Evidence
`src/fitdocs/connectors/credentials.py:163-167`.

## How to pick it up
Catch `OSError` around `path.stat()`, raise `CredentialStoreError` naming the
file, and add tests for both error classes.
