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
