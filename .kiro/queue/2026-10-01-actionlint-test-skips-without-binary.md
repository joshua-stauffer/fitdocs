---
id: 2026-10-01-actionlint-test-skips-without-binary
title: "test_actionlint_if_available skips locally although `uvx --from actionlint-py actionlint` works"
status: open
importance: low
importance_why: "actionlint is effectively enforced nowhere locally; same pattern in test_ci_workflow.py."
effort: S
kind: chore
area: tests/test_docs_workflow.py, tests/test_ci_workflow.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "do: see .kiro/queue/2026-10-01-actionlint-test-skips-without-binary.md -- test_actionlint_if_available skips locally although `uvx --from actionlint-py actionlint` works"
context:
  - tests/test_docs_workflow.py
  - tests/test_ci_workflow.py
blocked_by: []
---

## What
Both workflow tests look for `actionlint` on PATH and skip otherwise. The uvx form works on this machine and in CI.

## Why it matters
Workflow syntax errors are caught only if a developer happens to run actionlint by hand.

## Evidence
- `tests/test_docs_workflow.py:607` skip 'actionlint is not installed in this environment' (pinned at ba76d03); every local run in this session showed the skip.
- `uvx --from actionlint-py actionlint .github/workflows/docs.yml` exits 0 locally.

## How to pick it up
1. Add a fallback to `uvx --from actionlint-py actionlint` when uvx is available (or decide CI-only and document it).
2. Apply to both tests; keep a skip when neither is available.
