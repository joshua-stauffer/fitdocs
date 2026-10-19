---
id: 2026-10-19-local-full-suite-hung-near-test-plugins
title: A local full `uv run pytest` hung for two hours at ~85% (near tests/test_plugins.py) on a tree CI passed in 34 minutes
status: open
importance: medium
importance_why: docs/releasing.md step 1 runs the full suite locally on the release commit; a hang there stalls the cut with no output, and nothing in the suite bounds a test's runtime.
effort: M
kind: bug
area: tests/test_plugins.py, pyproject.toml [tool.pytest.ini_options], docs/releasing.md
created: 2026-10-19
surfaced_by: 0.2 pre-release landing (local gates on chore/docs-0-2)
pinned_at: c93f270
resume_command: "do: reproduce the local full-suite hang near tests/test_plugins.py with faulthandler_timeout set, find the spinning test from its traceback, fix it, and decide whether the suite should carry a per-test timeout"
context:
  - tests/test_plugins.py
  - pyproject.toml
  - docs/releasing.md
  - .github/workflows/ci.yml
blocked_by: []
---

## What

A serial local `uv run pytest -q -p no:cacheprovider` in the worktree of
`chore/docs-0-2` (tip `c93f270`, now `main`) stopped making progress at about
85% and sat at 100% CPU for 1 h 55 min until it was killed. CI run
39291225158 passed the identical commit in 34 minutes (`gates`, 3.12, 3.13),
and three earlier local full runs that day, on trees differing only in docs and
the regen/changelog commits, finished in 24-27 minutes.

## Why it matters

`docs/releasing.md` step 1 has the maintainer run the full suite locally on
the exact release commit. A silent hang there looks like a slow suite: the run
prints nothing, and nothing bounds a test's runtime, so the cut stalls until
someone notices. The same unbounded shape in CI is
[[2026-10-13-ci-jobs-have-no-timeout]].

## Evidence

- `ps` at 19:01 UTC: one `pytest` process, elapsed 01:55:50, 100.0% CPU; no
  other pytest process on the machine (the two earlier runs stopped that
  session had exited). A long-running `scripts.build_site serve` from another
  session was also alive.
- Progress: 23,511 of 27,039 collected tests had reported (counted from the
  `-q` dot stream). Collection order at that point is in
  `tests/test_plugins.py`: `test_relative_nested_path_resolves_against_data_root`,
  `test_absolute_path_is_used_as_given`,
  `test_plugin_settings_error_is_a_settings_error`,
  `test_no_plugins_reports_builtins_only_and_registry_unchanged`. The first
  three are pure path or type checks that cannot spin, so the dot count is
  probably off by a few; a discovery test nearby is the likelier suspect.
  **Unverified**: which test was running.
- `uv run pytest tests/test_plugins.py` alone at `c93f270`: 50 passed in
  0.34 s. So the hang depends on earlier tests' state or on the environment.

## How to pick it up

1. Re-run the full suite locally with `-o faulthandler_timeout=600`. Python's
   faulthandler dumps every thread's traceback when a test exceeds the bound,
   which names the spinning test and the line it is spinning on.
2. If it does not reproduce, try running `tests/test_p*.py` after the
   preceding directories in collection order, to find the state-dependent
   pair.
3. Decide whether to set `faulthandler_timeout` (or add `pytest-timeout`) in
   `[tool.pytest.ini_options]`, so a future hang fails loudly with a
   traceback, locally and in CI.

Done when the spinning test is named and fixed, or the hang is shown to be
environmental and the suite fails loudly instead of hanging.
