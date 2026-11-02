---
id: 2026-11-01-socket-guards-blind-to-unresolvable-hosts
title: 'Socket guards outside tests/connectors patch only socket.socket and miss unresolvable-host requests'
status: open
importance: low
importance_why: A test could contact the resolver and still pass: getaddrinfo fails first and is swallowed as a transport error.
effort: S
kind: gap
area: tests/test_confinement.py, tests/test_cli_derive.py, tests/wellness, tests/recovery
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 7.1 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-socket-guards-blind-to-unresolvable-hosts.md] Apply the hardened network guard to the seven remaining tests"
context:
  - tests/connectors/conftest.py
  - tests/test_confinement.py
  - tests/test_cli_derive.py
  - tests/wellness/test_e2e.py
  - tests/wellness/apple/test_determinism.py
  - tests/recovery/test_e2e_recovery.py
blocked_by: []
---

## What
Task 7.1 hardened the guard inside tests/connectors (4cc956a6). Seven other guards still patch only `socket.socket`. A request to an unresolvable host raises in `getaddrinfo` before any socket is created, and the connector layer swallows it as a transport error, so the guard never fires.

## Why it matters
These tests assert "no network" and cannot detect a network attempt that dies at name resolution.

## Evidence
- `tests/test_confinement.py:1090`, `:1519`, `:2991`; `tests/test_cli_derive.py:1126`; `tests/wellness/test_e2e.py:49`; `tests/wellness/apple/test_determinism.py:232`; `tests/recovery/test_e2e_recovery.py:85` each `monkeypatch.setattr(socket, "socket", ...)`.

## How to pick it up
1. Copy the hardened guard from tests/connectors (also patches `socket.getaddrinfo` and `create_connection`) into a shared fixture.
2. Replace the seven sites.
3. Mutation check: make a test call `requests.get('http://no-such-host.invalid')`; it must go red.
