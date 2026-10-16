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
  - tests/load/conftest.py
  - tests/load/test_settings.py
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

## Additional load-scope evidence (2026-10-16)

The same selector-order symptom recurred during hr-derivation task 1.2 repair
based on HEAD `578eabf`, before the final test-only recorder refinement
(frozen source snapshot
`c10a533fd5d9ff1e75118316844e0b03d670328f718c0ed4b94790a74ac6d653`).
The corresponding completed repair is 2a512eadb66de8e24dd0f0519c25e77b4d06b562; the receipts below
describe that earlier working-tree state, not a replay on the final commit.
No pytest dependency, test configuration or shared conftest was changed.
The repair implementer executed these commands; the controller independently
read their actual logs/exits and the local loader excerpt. No repair-free
baseline replay is claimed for this additional observation.

Using `UV_CACHE_DIR=/private/tmp/fitdocs-hr-uv-cache UV_OFFLINE=true uv run --no-sync`:

- `pytest tests/performance/test_engine.py tests/load/test_profile.py tests/hr_benchmarks tests/test_cli_derive.py tests/load/test_settings.py tests/test_contract_consumers.py -q`: exit 1, 2,190 passed / 2 fixture-lookup setup errors in 46.97 s. Both errors are `isolated_registry` missing in the invalid sufficiency/priority load-settings cases; the fixture is defined in `tests/load/conftest.py`.
- Identical selectors grouped load-first, `pytest tests/load/test_profile.py tests/load/test_settings.py tests/performance/test_engine.py tests/hr_benchmarks tests/test_cli_derive.py tests/test_contract_consumers.py -q`: exit 0, 2,192 passed in 49.56 s.
- The isolated load-settings node control passes: exit 0, one passed in 0.77 s.

Receipts are `/private/tmp/hr-accepted-overlay-repair-evidence/`:
`sandbox-scoped.log/.exit` (the filename records the initial invocation,
not a sandbox-denial cause),
`interrupted-full-before-policy-recorder/scoped.log/.exit`,
`scoped-fixture-control.log/.exit`, `sandbox-gates.json`,
`interrupted-full-before-policy-recorder/gates.json`,
`fixture-invocation-note.md` and `pytest-registration-excerpt.txt`.
The failing/grouped log SHA256 values are respectively
`8a52f97bbf424c7b648835470610d01de41c562264396850e4fa3a82b708cdd9`
and `4c47ffc85dcee175425c5c637a128b9d14de770ac60ad179ec8df91ead338eb7`.
Local pytest 9.1.1 source defers conftest fixture parsing via
`FixtureManager._pending_conftests` until `pytest_make_collect_report`
processes the matching Directory collector. This is corroborating evidence
for the already tracked selector/Directory defect; keep the existing upstream
issue and grouped-selector workaround, rather than adding a repository
conftest shim or treating the setup errors as a product regression.
