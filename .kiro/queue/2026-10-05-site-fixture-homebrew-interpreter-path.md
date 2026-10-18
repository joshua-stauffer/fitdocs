---
id: 2026-10-05-site-fixture-homebrew-interpreter-path
title: Docs-site fake-interpreter fixture fails with Homebrew Python
status: open
importance: low
importance_why: A fresh worktree can fail an unrelated site test despite installed tooling; pyenv provides a verified workaround.
effort: S
kind: bug
area: docs-site, tests/sitebuild/test_repo_wiring.py
created: 2026-10-05
surfaced_by: /kiro-impl analytics-index task 1.1
pinned_at: c38abdc
resume_command: "do: repair docs-site's fake-interpreter fixture so its installed-tool pin works with both Homebrew and pyenv Python; reproduce the failure from this queue item first"
context:
  - tests/sitebuild/test_repo_wiring.py
  - tests/sitebuild/conftest.py
  - .kiro/specs/docs-site/tasks.md
blocked_by: []
---

## What

`_run_inner_pytest` symlinks a fake interpreter to `sys._base_executable`
and places a synthetic `zensical` file beside it. With Homebrew Python,
the inner fixture's `Path(sys.executable).parent` check does not find that
file. The installed-tool positive control fails although the intended
synthetic executable exists.

## Why it matters

The default `uv sync` in a fresh worktree selected Homebrew Python 3.11.15
on this machine. An unrelated dependency change then appeared to break
site tooling. Matching main's pyenv interpreter resolved the failure,
but the test should not depend silently on that local interpreter choice.

## Evidence

At `c38abdc`, task 1.1's Luna implementer reported a scoped run with
771 passed, 35 skipped and one failure:
`test_requires_zensical_passes_when_the_tool_is_installed` expected
`1 passed`; the inner run raised
`Failed: site tooling not installed: uv sync --group docs` and reported
`1 error`. Installing the docs group did not repair the synthetic fixture.
The failing run was reported by the implementer; the controller did not
rerun it on Homebrew independently.

The controller independently checked the machine-local venv paths:
main used `/Users/josh/.pyenv/versions/3.11.15/bin/python3.11`, and the
worktree used `/opt/homebrew/opt/python@3.11/bin/python3.11`.
On unchanged main,
`uv run pytest tests/sitebuild/test_repo_wiring.py::test_requires_zensical_passes_when_the_tool_is_installed -q`
passed (`1 passed in 2.75s`). Recreating only the worktree venv with
the pyenv interpreter resolved the failure; an independent reviewer
subsequently passed the entire CI boundary/sitebuild set (807 tests).

The helper is at `tests/sitebuild/test_repo_wiring.py:145-178` and its
positive control at `:219-227`; the fixture checks the interpreter's
parent in `tests/sitebuild/conftest.py`.

## How to pick it up

1. Read the helper and `requires_zensical` fixture. Reproduce the positive
   control in a throwaway worktree using Homebrew Python; capture the
   inner `sys.executable` and its relation to the synthetic tooling path.
2. Repair the synthetic interpreter setup without weakening the
   installed-tool, absent-tool or required-tool assertions. Keep all
   files in temporary test directories.
3. Run all four `requires_zensical` tests on both available Python
   distributions, followed by the docs-site suite. The installed-tool
   case must pass and the missing-tool cases must retain their intended
   skip/error behavior.


## 2026-10-07 analytics-query recurrence

Task 1.1's independent review reproduced the installed-tool failure in the
fresh Homebrew 3.11.15 worktree (full regression log outside Git:
`/private/tmp/review-task11-fullsuite.log`). The parent then reproduced the
helper's symlink control in isolated temporary directories, using each
environment's `sys._base_executable` and placing a fake `zensical` next to
the fake interpreter: Homebrew returned `False`, main's pyenv 3.11.15
returned `True` for the exact `Path(sys.executable).parent` existence check.

The worktree environment was retained outside the repository, then recreated
with main's pyenv interpreter and the locked docs group. The task's production
code and this upstream fixture were not changed. A separate cold-cache failure
in the initial full run was repaired by warming an isolated UV cache with the
locked dependency set, rather than modifying tests or dependencies.

## 2026-10-18 root cause and a CI-matching workaround

Fresh-machine setup at `51d0e09`: `uv sync --group docs` picked Homebrew's
framework build (`/opt/homebrew/Cellar/python@3.11/3.11.11/Frameworks/Python.framework/...`)
and `FITDOCS_REQUIRE_SITE_TOOLING=1 uv run --group docs pytest tests/sitebuild`
gave `1 failed, 736 passed`, with this item's test the only failure. Mechanism,
verified directly: symlink `fakevenv/bin/python` to that `sys._base_executable`,
run it, and `sys.executable` prints `/opt/homebrew/opt/python@3.11/bin/python3.11`,
not the symlink's path. The macOS framework launcher re-resolves the
executable, so `Path(sys.executable).parent` never sees the fake venv's `bin/`.
So any macOS *framework* Python breaks the test, not only Homebrew's.

Workaround that matches CI (`.github/workflows/ci.yml` runs
`uv python install 3.11`, a python-build-standalone build):
`uv python install 3.11 && rm -rf .venv && uv sync --group docs --managed-python`.
The same suite then gave `737 passed`. A fix to the helper could compare
against the inner run's own `sys.executable` (as captured by a probe) instead
of assuming the symlink path survives, or skip the positive control with a
stated reason when `sys._framework` is set; either way, keep all four
`requires_zensical` assertions discriminating.
