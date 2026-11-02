---
id: 2026-11-01-connectors-neutral-scan-loopback-literals
title: 'The connectors neutral scan flags loopback literals as service hosts'
status: open
importance: medium
importance_why: Any test or doc that shows a loopback URL (127.0.0.1, ::1) fails the scan, which pushes authors to either weaken the scan or avoid the realistic example.
effort: S
kind: inconsistency
area: tests/connectors/test_docs.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 6.2 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-connectors-neutral-scan-loopback-literals.md] Admit loopback IP literals in the connectors neutral scan"
context:
  - tests/connectors/test_docs.py
  - docs/relay.md
  - docs/connectors.md
blocked_by: []
---

## What
The reserved-host list admits `localhost` but not the loopback literals `127.0.0.1` and `::1`. The relay docs say fitdocs accepts a loopback address for a non-https relay URL, so docs and tests that demonstrate it are flagged.

## Why it matters
The scan can only be satisfied by writing `localhost` everywhere, which hides the literal-address case the product actually supports.

## Evidence
- `tests/connectors/test_docs.py:904-905`: `_RESERVED_EXACT_HOSTS = frozenset({"example.com", "example.org", "example.net", "localhost"})`; `:930` uses it.
- `tests/connectors/test_docs.py:859` asserts the text "exactly `localhost`, `127.0.0.1` and `::1`" is documented, so the literals are already treated as legitimate elsewhere.

## How to pick it up
1. Add the loopback literals to the reserved set (parse the host with `ipaddress` and accept `is_loopback`).
2. Add a positive and a negative test (a non-loopback literal such as 203.0.113.5 must still be flagged).
3. Done when a loopback URL in a docs example passes.
