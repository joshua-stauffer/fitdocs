---
id: 2026-07-26-load-test-helper-duplication
title: Four load test modules carry near-verbatim copies of the same fixture helpers
status: open
importance: low
importance_why: Pure test hygiene; a fifth copy lands with each new load spec.
effort: S
kind: chore
area: training-load, tests/load/
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: c3d2201
resume_command: "do: Extract the duplicated _build_data_root / _docs_of / _write_load_settings / _RecordingSession / _table_count helpers in tests/load/ into a shared non-test module, and adopt isolated_registry in the two 6.x e2e modules"
context:
  - tests/load/test_engine.py
  - tests/load/test_feature_e2e.py
  - tests/load/test_arbitration_e2e.py
  - tests/load/test_migration_e2e.py
  - tests/load/conftest.py
blocked_by: []
---

## What
`_build_data_root`, `_docs_of`, `_write_load_settings`, a recording session class and `_table_count` are duplicated across `test_engine.py`, `test_feature_e2e.py`, `test_arbitration_e2e.py`, `test_migration_e2e.py` and `test_cli_load.py`. Separately, the two new 6.x e2e modules register calculators directly rather than through the `isolated_registry` fixture every comparable `test_engine.py` test uses.

## Why it matters
Low. The duplication was deliberate -- tasks 6.1-6.3 were each required to own a disjoint module -- and a shared helper module would not have violated that. The `isolated_registry` omission is a fail-open dependency: it is safe today (no built-ins ship, the leakage guard is green) but would silently change the meaning of the two-broad-supporter arbitration tests if any peer test leaked a `Modality.OTHER` calculator.

## Evidence
`grep -n 'def _build_data_root\|class _RecordingSession' tests/load/*.py` shows three definitions of each. `tests/load/test_arbitration_e2e.py:668-687,709-723` registers directly, versus `tests/load/test_engine.py:916-918,1108-1111` which uses the fixture. Verified at 3121bb6.

## How to pick it up
Add `tests/load/_helpers.py` (not a `test_` module, so pytest will not collect it) and move the shared helpers there. Then switch the 6.x modules to the `isolated_registry` fixture. Done when the suite is still at 1852 passed and each helper has one definition.
