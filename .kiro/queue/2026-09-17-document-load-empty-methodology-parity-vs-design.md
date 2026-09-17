---
id: 2026-09-17-document-load-empty-methodology-parity-vs-design
title: `document_load` accepts an empty-string methodology (parity with `_read_load`) while the design says non-empty
status: open
importance: medium
importance_why: Two readers of the same frontmatter must agree; the design's `LoadReading.methodology  # non-empty` comment is false today, and `_observed_counts` would count `""` as a methodology and could infer it.
effort: S
kind: inconsistency
area: plan-resolution, load-history, wiki-contract, src/fitdocs/contract.py, src/fitdocs/history/documents.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 1.1 review; /kiro-validate-impl design dimension)
pinned_at: fbba78b
resume_command: "do: decide whether both readers reject an empty-string methodology (one coordinated change to contract.document_load and history/documents._read_load plus their parity table) or amend design.md ContractReaders' non-empty comment to 'a str'; record the decision in .kiro/specs/plan-resolution/design.md"
context:
  - src/fitdocs/contract.py
  - src/fitdocs/history/documents.py
  - tests/test_contract.py
  - .kiro/specs/plan-resolution/design.md
blocked_by: []
---

## What
`contract.document_load` mirrors `history/documents._read_load` line for line
and both accept `load_methodology: ""` (returning `LoadReading(150.0, "")` /
`(150.0, "")`). Design § ContractReaders states the reading's methodology
"must be a non-empty str" and simultaneously requires exactly the private
reader's rule plus the postcondition `document_load(fm) is None iff
_read_load(fm) == (None, None)` — the two statements conflict on `""`.

## Why it matters
`_observed_counts` counts whatever methodology the reader returns, so `""`
could be inferred as the methodology; a page written by hand with an empty
value is not rejected by either reader. The parity table in
`tests/test_contract.py` pins today's agreement on that shape, so whichever
way the decision goes it is one coordinated edit.

## Evidence
- Probe (1.1 review): `_read_load({"load_value": 150, "load_methodology": ""}) == (150.0, "")`; `document_load(...)` returns `LoadReading(150.0, "")`.
- `tests/test_contract.py::_LOAD_PARITY_CASES` includes `{"load_value": 150, "load_methodology": ""}`.
- Implementation Note 1.1.

## How to pick it up
1. Read both readers and the parity table.
2. Pick: reject `""` in both (load-history owns `_read_load`; update its tests and the parity table) or amend the design comment. Either way one commit.
