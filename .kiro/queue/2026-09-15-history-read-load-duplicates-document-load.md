---
id: 2026-09-15-history-read-load-duplicates-document-load
title: '`history.documents._read_load` becomes a private duplicate of `contract.document_load` once plan-resolution lands'
status: open
importance: low
importance_why: Two readers of the same three keys with the same rule, in two modules; they agree today and nothing but a mutation would tell when they stop.
effort: S
kind: inconsistency
area: load-history, wiki-contract, src/fitdocs/history/documents.py, src/fitdocs/contract.py
created: 2026-09-15
surfaced_by: /kiro-spec-batch (Phase 7 wave 2, plan-resolution design)
pinned_at: b381f0d
resume_command: "do: once plan-resolution task 1.1 has landed contract.document_load, make history.documents._read_load call it (or delete it and read through the contract directly), add LoadReading/document_load to history.documents' CONTRACT_BINDINGS entry, and add _read_load to FORBIDDEN_LOCAL_NAMES so a revert is caught [queue: .kiro/queue/2026-09-15-history-read-load-duplicates-document-load.md]"
context:
  - src/fitdocs/history/documents.py
  - src/fitdocs/contract.py
  - tests/test_contract_consumers.py
  - .kiro/specs/plan-resolution/design.md
blocked_by: [plan-resolution]
---

## What
`src/fitdocs/history/documents.py:130-160` (`_read_load`) reads `load_value`
and `load_methodology` from a page's frontmatter with a five-clause rule
(`bool` rejected, `int`/`float` converted, `OverflowError` and non-finite
rejected, methodology must be a `str` or both are dropped). plan-resolution's
design (`.kiro/specs/plan-resolution/design.md`, ContractReaders) adds
`contract.document_load` with exactly that rule, so the reconciler reads
load through the contract like every other field. Once it lands, the history
package carries a private duplicate of a contract reader -- the class of
drift `tests/test_contract_consumers.py` exists to prevent, and the reason
`docio` was created (its module docstring records the last time a copy
"silently fell behind").

## Why it matters
Low today: plan-resolution's task 1.1 pins the two by a parity table (the
reading is absent exactly when `_read_load` returns `(None, None)`), so a
divergence reds. But the pin lives in plan-resolution's tests, not history's,
and a later edit to `_read_load` alone (say, accepting a numeric string)
would make the history page and the block page disagree on a page's load
while every history test stays green.

## Evidence
At `e40e361` (re-created as b381f0d after the 2026-09-16 .git loss, identical tree):

```
sed -n 130,160p src/fitdocs/history/documents.py      # _read_load, the five-clause rule
grep -n "document_load" src/fitdocs/contract.py          # (none yet -- added by plan-resolution 1.1)
grep -n "_read_load" tests/test_contract_consumers.py    # (none -- not in FORBIDDEN_LOCAL_NAMES)
```

The plan-resolution design deliberately leaves `history/documents.py`
untouched (its Out of Boundary list) and states this item there.

## How to pick it up
1. Confirm `contract.document_load` and `contract.LoadReading` exist (plan-resolution 1.1 merged).
2. Replace `_read_load`'s body with a call to `document_load` (returning `(reading.value, reading.methodology)` or `(None, None)`), or inline the reader at its one call site in `scan_documents`; keep `PageRecord`'s shape.
3. Append `"LoadReading"`/`"document_load"` to `CONTRACT_BINDINGS["fitdocs.history.documents"]`, add `"_read_load"` to `FORBIDDEN_LOCAL_NAMES` if the helper is removed, and run `uv run pytest tests/history tests/test_contract_consumers.py`. Done looks like: one implementation of the load-reading rule in `src/`, and the history documents tests green unedited.

## Open questions
- Whether `LOAD_KEYS` should stay bound by `history.documents` after the change (it is unpacked there only to feed `_read_load`); if the reader takes over, the binding entry shrinks and the `_LOAD_*_KEY` unpack goes.
