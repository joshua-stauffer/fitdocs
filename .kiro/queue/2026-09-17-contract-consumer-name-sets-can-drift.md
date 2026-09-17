---
id: 2026-09-17-contract-consumer-name-sets-can-drift
title: Two hand-maintained contract-consumer name sets have no test asserting they agree, and no key constant is pinned as spelled once
status: open
importance: low
importance_why: The boundary test's docstring says it checks "the names CONTRACT_BINDINGS registers" but compares to its own dict; a re-spelled key inside contract.py survives every pin.
effort: S
kind: gap
area: wiki-contract, tests/plans/test_boundary.py, tests/test_contract_consumers.py, tests/test_contract.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 1.1 and 2.1 reviews)
pinned_at: fbba78b
resume_command: "do: add one assertion that _CONTRACT_FROM_IMPORT_NAMES (tests/plans/test_boundary.py) equals CONTRACT_BINDINGS (tests/test_contract_consumers.py) for every plans module, and an AST scan over src/fitdocs/contract.py asserting each *_KEY value appears as a string constant exactly once"
context:
  - tests/plans/test_boundary.py
  - tests/test_contract_consumers.py
  - tests/test_contract.py
  - src/fitdocs/contract.py
blocked_by: []
---

## Evidence
- 2.1 round-1 review: `grep -n CONTRACT_BINDINGS tests/plans/test_boundary.py` finds only prose.
- 1.1 round-1 review: re-spelling `SPORT_KEY` as the literal `"sport"` inside `MANAGED_KEYS` leaves the suite green (published-schema and named-constant pins are by value); the absorbed queue item `2026-07-26-date-key-has-no-constant`'s "done looks like: `"date"` exactly once in src/" is true today (grep) but unpinned.
