---
id: 2026-11-06-suite-two-minute-budget
title: The CI test step takes 3m20s-5m16s against a 2-minute target; the maintainer has to choose the CI target
status: open
importance: medium
importance_why: The local target is met and CI fell from about 28 min, but the 7-minute CI budget is a placeholder until the maintainer sets the real target.
effort: M
kind: chore
area: tests/conftest.py, tests/connectors/conftest.py, pyproject.toml, .github/workflows/ci.yml, tests/test_ci_workflow.py, conftest.py, tests/test_bytecode_hygiene.py
created: 2026-11-06
surfaced_by: maintainer-requested test suite audit (target: 2 minutes for the complete suite)
pinned_at: a6038449
resume_command: "do: Ask the maintainer for the CI target in .kiro/queue/2026-11-06-suite-two-minute-budget.md (see its Update section), then set timeout-minutes in .github/workflows/ci.yml to match, adding shards only if they choose a target the current 4-vCPU run cannot meet"
context:
  - tests/conftest.py
  - tests/connectors/conftest.py
  - pyproject.toml
  - .github/workflows/ci.yml
  - tests/test_ci_workflow.py
  - conftest.py
  - tests/test_bytecode_hygiene.py
  - src/fitdocs/inbox.py
blocked_by: []
---

## What

The root suite is 32,696 tests (14,004 functions, 554 modules) and runs
serially. `pytest`'s numbered `mktemp` scans the whole base temp directory on
every call (`_pytest/pathlib.py` `make_numbered_dir` -> `find_prefixed`). Two
autouse fixtures call it for every test (`_isolate_index_directory` in
`tests/conftest.py`, `_isolated_connector_environment` in
`tests/connectors/conftest.py`), so the directory grows with the run and the
cost is quadratic in test count.

## Why it matters

`ci.yml` takes 26-30 min on every push that touches anything outside
`.kiro/specs/`, about 34 runs a day. Branch CI is the only full-suite run most
sessions get, so this wait sits in every implementation loop.

## Evidence

All on one commit (a6038449) on a 14-core M4 Pro, with no failures in any run
below (32,649 passed and 47 skipped, less the deselected tests in the last row):

| Configuration | Wall |
|---|---|
| Today: serial | 17m43s (setup 729 s, call 306 s, teardown 3 s) |
| xdist `-n 4`, nothing else | 3m21s |
| Two fixtures changed, serial | 7m07s |
| Two fixtures changed, `-n 4` | 2m16s |
| Two fixtures changed, `-n 10` | 1m21s |
| Two fixtures changed, `-n 14` | 1m28s (efficiency cores drag it) |
| Two fixtures changed, `-n 4`, 91 tests at or over 0.5 s deselected | 1m21s |

A sampling profile of the serial run put 65.4% of samples in `find_prefixed`.
Fixture self time: `_isolate_index_directory` 514 s, `tmp_path` 133 s,
`_isolated_connector_environment` 43 s. Setup per test rose from 6 ms to 38 ms
across the run.

Tried and rejected, so nobody repeats them:

- `-o tmp_path_retention_policy=none` under xdist: 5,697 tests fail with
  `FileNotFoundError`.
- `--capture=sys`: no gain (2m15s against 2m16s).
- Pruning for speed: after the fixture change a test costs about 3 ms of
  overhead, so removing 10,000 tests saves about 10 s at `-n 4`. Pruning is a
  maintenance decision (`2026-11-06-test-suite-pruning-decisions`), not a speed
  one.

This paragraph predates the work; the measured result is in the Update section below. The same suite takes 1,528-1,796 s
serial in CI against 1,063 s locally (1.4-1.7x, and one earlier run spread from
1,094 to 1,685 s across jobs), and a 4-vCPU runner may be hyperthreaded. That
puts `-n 4` with the fixture change at roughly 3-5 min in CI, and with the slow
tests fixed at roughly 2-3 min. These are estimates until a real run.

## How to pick it up

1. **Fixtures.** In both autouse fixtures, make one session-scoped base directory
   with `tmp_path_factory.mktemp` and create `base / str(next(counter))` per
   test. Keep the `mkdir`. Leave `tmp_path` alone: at `-n 4` its self time is about
   14 s of worker time across 11,720 uses, so 3-4 s of wall.
2. **Parallelism.** Add `pytest-xdist` to the dev group and run `-n auto` in CI
   (`tests/test_ci_workflow.py:463` pins that step's `run` to exactly `uv run pytest`,
   so it changes in the same commit). Nine full parallel runs were clean.
   Known load-sensitive tests are in `2026-10-12-query-interrupt-test-flake-under-load`.
3. **Measure in CI** before tuning further. Shards are the next lever if the test
   step is still over budget: Actions minutes are free on a public repository.
4. **Slow tests**, by measured serial cost:
   - 41 s in `inbox.settle`: seven modules drive a real drain at the default
     `settle_seconds` of 2.0 (`test_cli_connectors`, `connectors/test_e2e`,
     `hr_benchmarks/test_determinism`, `test_cli_encoder_preflight`,
     `hr_benchmarks/test_e2e`, `recovery/test_cli_recovery`,
     `test_cli_sync_inbox`).
   - 30 s in two real-SIGINT tests (`query/test_interrupt`,
     `dashboards/test_interrupt`).
   - 12.6 s in a nested pytest (`test_ci_workflow.py::test_the_test_step_env_really_arms_the_forbidden_strings_guard`).
   - 10 s in a real lock wait (`query/test_cli_query.py::test_real_busy_holder_uses_fixture_pid_not_controlled_pid`).
   - 9.9 s running `--help` for every installed command (`test_packaging.py`).
   - 8 s in real tile fetches (`2026-11-06-tests-contact-openstreetmap`).
5. **Local bytecode, optional.** The root `conftest.py` purges `src/` bytecode and
   turns off writing for the whole run. With it on, collection falls from 16 s to
   2.3 s when warm and `-n 4` from 2m16s to 1m46s. That protection exists for
   mutation evidence, so a replacement must keep it: checked-hash `.pyc` files for
   `src/` validate against source content, which a same-size, same-second mutation
   cannot fool. CI starts cold, so this helps local runs only.
6. **Ratchet.** Add `--durations` to CI and a budget check so the time cannot
   quietly return. The suite went from about 27,000 tests on 2026-10-19 to 32,696
   today.

Done means a real CI run of the test step within the budget the maintainer sets,
and the suite still green on all three interpreters.

## Update 2026-11-06: what landed

The maintainer approved steps 1-4 and 6 of "How to pick it up" and ruled out step 5 (local bytecode) for now. Landed: the fixtures, `pytest-xdist` with `uv run pytest -n auto` in CI, the release gates and the documented validation, the settle, lock wait, nested pytest, `--help` and tile fixes, `--durations=25` in CI's log, and `timeout-minutes: 7` on the test step.

Measured:

- Local, full suite: 1m17s with `-n auto`, 1m49s with `-n 4`.
- CI, with 4 workers on all three interpreters: 3m20s-5m16s over nine job runs. Identical commits varied by more than 50%, so one run says little. About 45-55 s of each is startup and collection.

Not done, on purpose:

- **The real-SIGINT tests keep 14 trials.** Cutting them to 5 was tried and reverted. With the regression `analytics-query/design.md` names, on the locked duckdb 1.5.6, a reviewer measured 3 misses in 13 runs at 5 trials (10 hangs in 45 trials, about 22% per trial, so about 29% missed at 5 trials and about 3% at 14). The saving was an estimated 4-5 s of wall time, on the check for a critical Ctrl-C hang. These tests do not saturate the runner: `src/fitdocs/query/sandbox.py:23` caps DuckDB at 2 threads.
- **No shards.** They would be the way to reach 2 minutes in CI: 2 shards per interpreter is 6 jobs, and splitting by path can silently drop a new directory unless something checks the partition. Pruning (`2026-11-06-test-suite-pruning-decisions`) saves little time, as noted under Evidence, so it would not close the gap.

## Open questions

- Is the target 2 minutes in CI (needs shards or a larger runner on current
  estimates) or 2 minutes locally and about 3 in CI?
