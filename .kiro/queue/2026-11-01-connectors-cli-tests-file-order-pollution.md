---
id: 2026-11-01-connectors-cli-tests-file-order-pollution
title: 'tests/connectors CLI tests depend on file order'
status: open
importance: low
importance_why: Order-dependent tests hide real state leaks and fail confusingly under a different runner configuration.
effort: M
kind: bug
area: tests/connectors/test_cli_connectors.py, tests/connectors/test_cli_relay_pull.py, tests/connectors/test_cli_relay_connect.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 8.4 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-connectors-cli-tests-file-order-pollution.md] Find and fix the cross-module state leak in the connectors CLI tests"
context:
  - tests/connectors
  - tests/conftest.py
blocked_by: []
---

## What
With `-p no:randomly` and a non-default file order, tests in `tests/connectors` fail with `KeyError: FITDOCS_CREDENTIALS_DIR` and `DuplicateConnectorIdError: 'personal-key'`. In directory order they pass. A module leaves process-global state (environment, connector registry) behind.

## Why it matters
A reordering (a new file, a different runner) can turn the suite red with no code change; the registry leak can also mask a real duplicate-id defect.

## Evidence
- Reproduce: `uv run pytest -q -p no:randomly tests/connectors/test_cli_relay_pull.py tests/connectors/test_cli_connectors.py tests/connectors/test_cli_relay_connect.py` (the 8.4 review ran a non-default order and saw both errors; the exact failing pair is not recorded, so bisect the order).

## How to pick it up
1. Find the pair by running each CLI test module after each other module.
2. Fix the leak with a fixture that restores the registry and environment.
3. Done when every pairwise order passes.
