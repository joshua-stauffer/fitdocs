---
id: 2026-09-17-forbidden-literals-omit-load-keys
title: The converted-consumer literal guard holds only the five matched-field keys, not `LOAD_KEYS`
status: open
importance: medium
importance_why: Req 1.2 names load value and methodology among the field names the contract alone may spell, but a converted module inlining `frontmatter.get("load_methodology")` is not structurally caught.
effort: S
kind: gap
area: plan-resolution ConsumerGuard, wiki-contract, tests/test_contract_consumers.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 2.1 round-3 review)
pinned_at: fbba78b
resume_command: "do: check every CONVERTED_MODULES entry for a literal load-key spelling, then widen FORBIDDEN_LITERALS in tests/test_contract_consumers.py by contract.LOAD_KEYS (by constant, never re-spelled) with a mutation in corpus.py proving it reds"
context:
  - tests/test_contract_consumers.py
  - src/fitdocs/contract.py
  - src/fitdocs/plans/corpus.py
blocked_by: []
---

## What
`FORBIDDEN_LITERALS` (tests/test_contract_consumers.py) was scoped by
plan-resolution design § ConsumerGuard to the five matched-field keys.
`LOAD_KEYS` (`load_value`, `load_methodology`) are not in it.

## Why it matters
Mutation `methodology = frontmatter.get("load_methodology") if load_reading
is not None else None` in `src/fitdocs/plans/corpus.py` leaves the guard
green (110 passed over corpus + consumers). The reader is still the only
spelling in practice, but the guard cannot prove it.

## Evidence
- 2.1 round-3 review: the mutation above survives `uv run pytest tests/plans/test_corpus.py tests/test_contract_consumers.py`.
- `tests/test_contract_consumers.py:298-306` (the tuple).

## How to pick it up
1. Grep every registered module for `"load_value"`/`"load_methodology"` string constants (render/load.py legitimately writes them? — check whether it is a registered module).
2. Add `*contract.LOAD_KEYS` to the tuple; run the mutation; commit.
