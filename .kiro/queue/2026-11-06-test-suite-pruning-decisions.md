---
id: 2026-11-06-test-suite-pruning-decisions
title: Test code is 4.5x production code, and matrices, scanner self-tests, doc bindings and workflow pins hold most of the redundancy
status: open
importance: medium
importance_why: Not a speed problem once the fixture fix lands, but 387k lines of tests are read and edited by every agent run, and the most-churned test files are pins rather than behaviour.
effort: L
kind: research
area: tests/, .kiro/steering/change-protocol.md
created: 2026-11-06
surfaced_by: maintainer-requested test suite audit
pinned_at: a6038449
resume_command: "do: Take the maintainer's decisions on .kiro/queue/2026-11-06-test-suite-pruning-decisions.md, then prove each proposed reduction by mutation on the critical-path modules before deleting anything"
context:
  - .kiro/steering/change-protocol.md
  - tests/connectors/test_wellness_pull.py
  - tests/render/charts/kit/test_reference_band.py
  - tests/recovery/test_boundary.py
  - tests/hr_benchmarks/test_purity.py
  - tests/test_docs_guarantees.py
  - tests/test_ci_workflow.py
blocked_by:
  - 2026-11-06-suite-two-minute-budget
---

## What

Coverage is 98.8% line and branch over 30,699 statements, with 387,643 lines of
test code against 86,620 of source. Measured per test with coverage contexts, on
arcs (executed edges, finer than lines):

- 1,518 of 14,004 test functions (11%) reach every arc the suite reaches; 636 reach
  95% and 94 reach 80%.
- Of 20,807 parametrized cases, 14,412 repeat exactly the arcs of another case of
  the same function. A greedy pick within each function needs 4,296.
- The 44 functions with 50 or more cases hold 5,971 tests; 227 of those cases reach
  the same arcs. For example `test_round2_all_registered_capability_roles` has 479
  cases over 13 distinct paths, and
  `test_listed_package_preserves_json_types_by_field_and_role` has 288 over one.
- 30 source-guard modules hold 2,117 tests and 28,659 lines. Only about 185 of those
  tests opened real source during the test (a lower bound, since a module-scoped
  cache hides reads). The rest feed synthetic strings to scanners that live in the
  tests themselves.
- 44 modules named for docs, changelogs or specs hold 1,058 tests and 15,973 lines.
- Workflow pins are 138 tests and 3,516 lines. Site tooling is 737 tests and 13,060
  lines, and all but `sitebuild/test_hero_chart.py` run no `fitdocs` code in process.

Arcs measure execution, not assertion strength. Two cases on the same arcs can
still pin different boundary values, so these are upper bounds on what can go.

## Why it matters

Editing cost, not run time: after the fixture fix, removing 10,000 tests saves about
10 s at `-n 4`. In the last 90 days the most-churned test files were
`test_public_api.py` (36 commits), `test_contract_consumers.py` (24),
`test_confinement.py` (22) and `test_agent_skill.py` (20). Doc modules such as
`connectors/test_docs.py` (18) and `index/test_contract_docs.py` (17) follow closely.

## Evidence

CI failure logs from 2026-09-19 to 2026-11-04 (195 failed `ci.yml` runs; 82 name
failing tests, the other 113 failed elsewhere or left empty logs): only 33 functions
went red, in 58 branch-level incidents. From each one-line message, roughly 10 were
behaviour or goldens, 12 prose, literal or surface pins, 9 environment or harness,
and 2 unclear.

No workflow or site test went red. No `round<N>` test did. Of the 50+ case matrices,
only `identity/test_boundary.py::test_closure_scanner_reads_every_form` did, a
scanner self-test that broke on a newer Python's AST. The clearest production catch:
`render/test_golden_docs.py::test_chart_assets_match_committed_goldens` on the CI
matrix branch, fixed by f7e66117 (hero-chart smoothing depended on the Python
version's `sum()`).

CI only sees what survives targeted local runs, so this undercounts what tests catch
during development. It is evidence about the full-suite gate, not about TDD value.

## How to pick it up

1. Get the maintainer's answers below.
2. Prove before deleting, per `change-protocol.md`'s Fixture Discrimination rule: run
   mutations over the critical-path modules (ingest, metrics, docmerge, contract,
   sync, inbox, identity, connector delivery and credentials) against the reduced
   set. A mutant the full suite kills and the reduced set misses means the reduction
   is wrong. The fixture fix makes this affordable, which is why it blocks this item.
3. Then, in order of evidence:
   - Collapse the 50+ case matrices to their distinct paths plus boundary values.
   - Replace per-module AST scanners with one shared scanner, or with ruff
     `banned-api` plus import-linter, keeping the real-tree checks.
   - Move site tooling tests behind `docs.yml`'s path filter.
   - Reduce workflow pins to `actionlint` plus the few that record a real past defect.
4. Add a process limit so matrices do not regrow: `change-protocol.md`'s mutation rule
   and review rounds are where `round<N>` tests came from. A parametrization over a
   set size (say 50 cases) could owe a stated reason.

## Open questions

- Purge doc-binding tests repo-wide? On 2026-11-03 the maintainer chose to stop adding
  them and delete those a change touches, and did not choose a repo-wide purge. Worth
  keeping either way: executable docs such as
  `query/test_skill_examples.py::test_every_skill_sql_fence_runs_and_returns_topic_rows`
  and code-against-document set equality such as `test_ownership_contract.py`.
- Keep bespoke AST guards at all, or accept what ruff and import-linter can express?
  The bespoke ones catch more spellings (dynamic imports, aliases).
