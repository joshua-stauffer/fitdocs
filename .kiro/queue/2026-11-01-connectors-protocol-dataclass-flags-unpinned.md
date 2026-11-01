---
id: 2026-11-01-connectors-protocol-dataclass-flags-unpinned
title: 'Connector protocol dataclass tests pin only `frozen`, not kw_only, eq, order or slots'
status: open
importance: low
importance_why: A change to any of those flags on a protocol dataclass changes the construction contract of every connector without a red test.
effort: S
kind: gap
area: tests/connectors/test_protocol.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 6.1 review (pre-existing)
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-connectors-protocol-dataclass-flags-unpinned.md] Pin all dataclass parameters in the protocol test helper"
context:
  - tests/connectors/test_protocol.py
  - src/fitdocs/connectors/protocol.py
blocked_by: []
---

## What
`_fields_and_defaults` pins field names, order, types and `frozen` for each protocol dataclass, but not the other dataclass parameters. This predates relay-server and covers every protocol dataclass, not only the relay's.

## Why it matters
kw_only, eq, order or slots can drift silently across the connectors protocol layer.

## Evidence
- `tests/connectors/test_protocol.py:86-106`: the helper asserts `cls.__dataclass_params__.frozen is frozen` and nothing else from `__dataclass_params__`.

## How to pick it up
1. Extend the helper to take and assert the remaining `__dataclass_params__` fields (or assert all of them equal to an explicit expected set).
2. Update each call site with the current values (read them from the classes).
3. Done when flipping `slots` on one dataclass turns a test red.
