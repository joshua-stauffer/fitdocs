---
id: 2026-10-08-pytest-interleaved-selector-fixture-loss
title: pytest 9.1.1 loses nested conftest fixtures when explicit selectors interleave directories
status: open
importance: medium
importance_why: A valid focused verification command errors during setup and can be mistaken for a product regression.
effort: S
kind: bug
area: tooling, pytest, tests/query
created: 2026-10-08
surfaced_by: /kiro-impl analytics-query task 7.3 debug
pinned_at: f7266f7
resume_command: "do: track pytest issue14971 and verify the supported pytest policy for nested/root/nested explicit selectors; retain grouping of same-directory selectors until an independently verified upstream fix [queue: .kiro/queue/2026-10-08-pytest-interleaved-selector-fixture-loss.md]"
context:
  - pyproject.toml
  - tests/query/conftest.py
  - tests/query/test_docs_analytics.py
  - .kiro/specs/analytics-query/tasks.md
blocked_by: []
---

## What

pytest 9.1.1 can create two Directory identities for the same nested directory
when explicit file selectors interleave nested, root, nested. Fixtures from
the nested conftest are visible only on the first identity. The source fix
belongs upstream to pytest; grouping identical-scope directory selectors is
the current harness correction. Do not add a downstream conftest shim.

## Why it matters

A focused test command can fail before a valid test executes, even though the
unchanged source passes with the same selectors grouped together. This has
already interrupted analytics-query verification.

## Evidence

Root independently reproduced on accepted f7266f7 with Python3.11.15,
pytest9.1.1, no plugin or source edits, private empty HOME:

- `uv run --offline --no-sync --all-groups pytest -q tests/query/test_fixtures.py tests/test_agent_skill.py tests/query/test_docs_analytics.py`: exit1,91passed/1error, `home_dir` missing for the docs catalog test at `tests/query/test_docs_analytics.py:98`.
- Same invocation with selectors `tests/query/test_fixtures.py tests/query/test_docs_analytics.py tests/test_agent_skill.py`: exit0,92passed.

Raw root receipts are `/private/tmp/analytics-query-parent-pytest-selector-control/`.
Fresh debugger separately traced distinct query Directory identities and
fixture visibility, reproduced the original new-example selector failure,
and passed the unchanged same81-test grouped scope. Detailed private report:
`/private/tmp/analytics-query-debug-docs-fixture-collection/REPORT.md`.
Official upstream issue: https://github.com/pytest-dev/pytest/issues/14971.
No alternate pytest version has been validated here. Normal directory-level
canonical selection is unaffected in the observed runs.

## How to pick it up

1. Read `pyproject.toml` and the upstream issue; verify the currently supported
   pytest version and issue resolution from primary sources.
2. Reproduce both commands above using a properly bound private environment,
   existing empty HOME and bytecode suppression. Preserve the failing receipt.
3. If changing dependency policy, verify an actual upstream fixed version with
   both selector orders, native directory selection and the full suite. Keep
   the harness grouping until that evidence exists; no query fixture workaround.
