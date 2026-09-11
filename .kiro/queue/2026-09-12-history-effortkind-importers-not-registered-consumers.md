---
id: 2026-09-12-history-effortkind-importers-not-registered-consumers
title: history/engine.py and history/series.py import EffortKind but are not registered contract consumers
status: open
importance: medium
importance_why: The contract-consumer guard (tests/test_contract_consumers.py) exists so a contract change is forced to visit every importer; two history modules bind a contract enum and are invisible to it, and design.md ~907 says documents.py is the only importer.
effort: S
kind: gap
area: load-history, src/fitdocs/history/engine.py, src/fitdocs/history/series.py, tests/test_contract_consumers.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 5.4 (reviewer round 2, FOLLOW_UPS)
pinned_at: 8cd0062
resume_command: "do: either route EffortKind through history/documents.py (re-export, so the package keeps one contract seam) or register engine.py and series.py in tests/test_contract_consumers.py; then fix the design.md 'only importer' sentence"
context:
  - src/fitdocs/history/engine.py
  - src/fitdocs/history/series.py
  - src/fitdocs/history/documents.py
  - tests/test_contract_consumers.py
  - .kiro/specs/load-history/design.md
blocked_by: []
---

## What
`grep -n "from fitdocs.contract import" src/fitdocs/history/*.py` lists
documents.py, page.py, engine.py, series.py. Task 5.4 registered the first
two by identity (from-import binding). `engine.py` and `series.py` import
`EffortKind` for the race/test filter and are unregistered.

## Evidence
5.4 review round 2 `FOLLOW_UPS`; the grep above at 8cd0062.

## How to pick it up
Prefer the re-export: `documents.py` already narrows the contract for the
package. Add the identity pins either way; the guard's docstring counts
consumers, update it.
