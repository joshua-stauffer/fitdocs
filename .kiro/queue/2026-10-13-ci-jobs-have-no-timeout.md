---
id: 2026-10-13-ci-jobs-have-no-timeout
title: No CI job sets timeout-minutes and the suite has no per-test timeout, so a single hanging test stalls a run for GitHub's six-hour default
status: open
importance: medium
importance_why: The suite now spawns real subprocesses and sends them SIGINT (query and dashboards interrupt tests), which is exactly the shape that hangs; a hang burns six hours of runner time and blocks the merge gate that main depends on.
effort: S
kind: gap
area: distribution, .github/workflows/ci.yml, .github/workflows/release.yml, .github/workflows/docs.yml, pyproject.toml
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 4.2 reviewer)
pinned_at: 0a98d5c
resume_command: "do: add timeout-minutes to every job in .github/workflows/{ci,release,docs}.yml (size each from a measured green run, with headroom) and decide whether to add pytest-timeout or a faulthandler timeout to pyproject.toml; pin the workflow edit by equality like the other workflow-body pins [queue: .kiro/queue/2026-10-13-ci-jobs-have-no-timeout.md]"
context:
  - .github/workflows/ci.yml
  - .github/workflows/release.yml
  - .github/workflows/docs.yml
  - pyproject.toml
  - tests/test_ci_workflow.py
  - tests/test_docs_workflow.py
blocked_by: []
---

## What
None of the three workflow files sets `timeout-minutes` on any job, and
`pyproject.toml` configures neither `pytest-timeout` nor
`faulthandler_timeout`. GitHub's default job limit is 360 minutes.

## Why it matters
A test that hangs on the runner (a child process that ignores SIGINT, a DuckDB
call that never returns, a lock wait) holds the job until the six-hour limit.
The hang-prone tests are real-process tests: `tests/query/test_interrupt.py`
and `tests/dashboards/test_interrupt.py` start the CLI and signal it, and a
related item records a hang that depends on the machine
(`2026-10-13-sigint-ignored-during-streaming-query-statements`). One earlier
suite hang already needed a bounded reproduction to find
(`.kiro/queue/closed/2026-07-30-power-fill-value-change-hangs-the-suite.md`
suggests `--timeout=60` or `faulthandler_timeout`).

## Evidence
At 0a98d5c:
- `grep -n "timeout-minutes" .github/workflows/*.yml` prints nothing.
- Jobs without a limit: `ci.yml` `gates` (line 40); `release.yml` `gates` (46), `version` (70), `build` (92), `check` (117), `verify-artifact` (159), `publish-testpypi` (196), `publish-pypi` (240), `verify-published` (272); `docs.yml` `build` (45), `deploy` (107).
- `grep -n "pytest-timeout\|timeout" pyproject.toml` finds no pytest timeout; `[tool.pytest.ini_options]` is `testpaths = ["tests"]`, `addopts = "-ra"` (lines 272-274).
- A full local run during dashboards task 2.2 finished `11839 passed, 44 skipped in 321.91s (0:05:21)` (the suite has grown since), so a limit of 30 minutes for `gates` would be generous; measure the CI figure before choosing.

## How to pick it up
1. Read `.github/workflows/ci.yml` and `tests/test_ci_workflow.py` to see how workflow bodies are pinned (the docs-site and distribution notes say to pin run bodies by equality); add the new key without breaking those pins, and update them in the same change.
2. Pull the duration of the last few green `gates` runs (`gh run list --workflow ci.yml --limit 10`, then `gh run view`), set `timeout-minutes` to roughly three times the slowest, and set shorter limits on the small release jobs.
3. Decide about a per-test timeout. `pytest-timeout` adds a dev dependency; `faulthandler_timeout` in `[tool.pytest.ini_options]` adds a traceback dump without a new dependency but does not abort. Done means every job has a limit and a hang shows a stack in the log.

## Open questions
Whether a per-test timeout is wanted at all (the real-process tests have their own bounded waits already); the job-level limit is the part with a clear case.
