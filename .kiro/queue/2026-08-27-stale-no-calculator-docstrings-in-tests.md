---
id: 2026-08-27-stale-no-calculator-docstrings-in-tests
title: Six test-module docstrings still say fitdocs ships no calculator; the new prose guards do not scan tests/
status: open
importance: low
importance_why: Prose that outlived the behaviour it describes, in the exact class the new corpus guard was built to prevent — but outside its corpus.
effort: S
kind: doc-drift
area: threshold-load, tests/
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
pinned_at: 3e14ab9
resume_command: "/kiro-impl threshold-load [queue: .kiro/queue/2026-08-27-stale-no-calculator-docstrings-in-tests.md] Correct the six docstrings and widen the guard's corpus"
context:
  - tests/test_docs_guarantees.py
  - tests/load/conftest.py
blocked_by: []
---

## What

Task 4.1 added two prose guards, but neither scans `tests/`:
`tests/test_docs_guarantees.py:61` scans README + `docs/**.md`;
`tests/test_plugin_regression.py:373` scans `fitdocs/plugins.py`. So six test
docstrings still assert the invariant this branch reversed:

`tests/load/conftest.py:3`, `tests/load/test_engine.py:14`,
`tests/load/test_cli_load.py:24`, `tests/load/test_feature_e2e.py:10`,
`tests/test_confinement.py:419`, `tests/test_plugins.py:367`.

Three of those files were **edited on this branch** without the docstring
being corrected. `conftest.py:3`'s "the first real methodology arrives from
`threshold-load`. Until then..." is doubly stale — it has now arrived.

## Why it matters

Low user impact; these are agent-facing. But it is precisely the class the
corpus guard exists to prevent, sitting outside its corpus — and the same
gap covers `CLAUDE.md` and `.kiro/steering/*.md`, which carry the same
invariant with no guard at all.

## Evidence

`3e14ab9`. `grep -rln "ships no\|registers no\|bundles no" tests/ CLAUDE.md .kiro/steering/`.

## How to pick it up

Correct the six docstrings, then decide whether the corpus guard should widen
to `tests/**` and the agent-facing prose (`CLAUDE.md`, `.kiro/steering/*.md`).
Widening to `tests/` risks false positives on deliberately-quoted forbidden
phrases — the guard's own `forbidden` list is one — so scope carefully.
