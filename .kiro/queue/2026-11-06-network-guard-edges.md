---
id: 2026-11-06-network-guard-edges
title: The tests' network guard leaves a few edges open: other socket events, misattributed attempts, unusual loopback spellings
status: open
importance: low
importance_why: Nothing in the suite hits any of these today; a future test would either go unnoticed or fail with a confusing attribution.
effort: S
kind: gap
area: tests/support/network.py, tests/conftest.py
created: 2026-11-06
surfaced_by: independent reviewer pass on the suite-speed work
pinned_at: 974aa3d5
resume_command: "do: Close the edges listed in .kiro/queue/2026-11-06-network-guard-edges.md in tests/support/network.py, each with a mutation-checked test in tests/support/test_network.py"
context:
  - tests/support/network.py
  - tests/support/test_network.py
  - tests/conftest.py
blocked_by: []
---

## What

- **False negatives.** The guard handles only the `socket.getaddrinfo` and `socket.connect` audit events. `socket.gethostbyname`, `gethostbyname_ex`, `gethostbyaddr` and `sendto` pass untouched.
- **Misattribution.** An attempt made while importing a test module fails whichever test's teardown runs next, and by reading a leaked thread would do the same. An attempt after the last teardown goes unreported.
- **False positives.** `127.1`, `localhost.` and `fe80::1%lo0` are refused although they stay on the machine. These fail loudly.

## Why it matters

The guard exists so that a test cannot quietly reach the network. Each gap is a way for that to happen unnoticed, or for the wrong test to take the blame.

## Evidence

A reviewer called the hook directly with those events and they returned allowed. Grep finds no user of them in `src` or `tests`. Misattribution was confirmed for an import-time attempt, serially and on each worker under `-n 2`.

## How to pick it up

1. Add the missing events to `_refuse_external`.
2. Decide whether attempts outside any test should fail the session in `pytest_sessionfinish`.
3. Widen `_is_local` only if a real test needs one of those spellings.
