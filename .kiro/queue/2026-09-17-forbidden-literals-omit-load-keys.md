---
id: 2026-09-17-forbidden-literals-omit-load-keys
title: The converted-consumer literal guard holds only the matched-field and base-identity keys, not `LOAD_KEYS`, `SOURCES_KEY` or `UUID_KEY`
status: open
importance: medium
importance_why: Req 1.2 names load value and methodology among the field names the contract alone may spell, but a converted module inlining `frontmatter.get("load_methodology")` is not structurally caught; the same holds for the `sources` and `uuid` keys the activity-identity scan reads through the contract's helpers.
effort: S
kind: gap
area: plan-resolution ConsumerGuard, wiki-contract, tests/test_contract_consumers.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 2.1 round-3 review); extended by /kiro-impl activity-identity 2026-10-01
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

## Evidence (2026-10-01 addendum, read at `fc5c06d`)
- activity-identity (task 3.1) added the four base-identity keys by spreading
  `*fitdocs.contract.SOURCE_IDENTITY_KEYS` into the tuple, but left out two keys
  that its scan reads through the contract's `source_refs` / `document_uuid`: `SOURCES_KEY` (`"sources"`, `contract.py:360`) and
  `UUID_KEY` (`"uuid"`, `contract.py:357`). `TYPE_KEY`, `GENERATOR_KEY` and
  `DOC_VERSION_KEY` (`contract.py:348-354`) are also absent. The tuple is now at
  `tests/test_contract_consumers.py:320-329` (the `:298-306` cited below is stale).
- Widening is green today: a scan with the guard's own `_module_ast` over the 20
  `CONVERTED_MODULES` finds none of `UUID_KEY`, `SOURCES_KEY`, `LOAD_KEYS`,
  `TYPE_KEY`, `GENERATOR_KEY`, `DOC_VERSION_KEY` spelled as a string constant.
- One real collision to plan around for `"uuid"`: `src/fitdocs/identity/matching.py:74`
  spells `UUID = "uuid"` as an `Evidence` enum value (a different vocabulary with
  the same spelling). `matching.py` is not in `CONVERTED_MODULES` today, so it
  does not red, but registering it later would; give `Evidence` a value that is
  not the key spelling or exempt it by name.

## Evidence (original, 2026-09-17)
- 2.1 round-3 review: the mutation above survives `uv run pytest tests/plans/test_corpus.py tests/test_contract_consumers.py`.
- `tests/test_contract_consumers.py:298-306` (the tuple).

## How to pick it up
1. Grep every registered module for `"load_value"`/`"load_methodology"` string constants (render/load.py legitimately writes them? — check whether it is a registered module).
2. Add `*contract.LOAD_KEYS` to the tuple; run the mutation; commit.
3. In the same change, add `contract.SOURCES_KEY` and `contract.UUID_KEY` (and
   decide on `TYPE_KEY`, `GENERATOR_KEY`, `DOC_VERSION_KEY`), each by constant
   and each with a mutation in the module that reads it (`identity/pages.py`,
   `plans/corpus.py`) proving it reds; see the `"uuid"` collision above.
