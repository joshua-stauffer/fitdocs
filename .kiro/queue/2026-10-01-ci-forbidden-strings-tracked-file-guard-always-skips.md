---
id: 2026-10-01-ci-forbidden-strings-tracked-file-guard-always-skips
title: "CI's `uv run pytest` never sets FITDOCS_FORBIDDEN_STRINGS, so the forbidden-strings scan over every tracked file always skips in CI"
status: open
importance: medium
importance_why: "The encumbered-content guard over tracked files runs only when a maintainer remembers to run it locally; new docs/fixtures merge unscanned."
effort: S
kind: gap
area: distribution, encumbered-content-purge, .github/workflows/ci.yml, tests/test_forbidden_strings.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "do: see .kiro/queue/2026-10-01-ci-forbidden-strings-tracked-file-guard-always-skips.md -- CI's `uv run pytest` never sets FITDOCS_FORBIDDEN_STRINGS, so the forbidden-strings scan over every "
context:
  - .github/workflows/ci.yml
  - tests/_forbidden_strings.py
  - tests/test_ci_workflow.py
  - .kiro/specs/distribution/design.md
blocked_by: []
---

## What
In `ci.yml` the pytest step runs before the secret is written to `$RUNNER_TEMP/forbidden-strings.txt`, and the variable is only passed to `check_artifacts`. `tests/_forbidden_strings.py` skips when the variable is unset, so `tests/test_forbidden_strings.py` (including its every-tracked-file scan) never runs in CI. `docs.yml` gates only the site trees.

## Why it matters
Every new tracked file (docs pages, fixtures, website assets, scripts) relies on a manual local run for the purge guard. docs-site added ~57 files; the controller ran the guard by hand before merge (clean), but nothing enforces that.

## Evidence
- `.github/workflows/ci.yml:56` `run: uv run pytest`; `:81` writes the match file afterwards; `:84` passes FITDOCS_FORBIDDEN_STRINGS only to check_artifacts (pinned at ba76d03).
- `tests/_forbidden_strings.py:158` skip: 'FITDOCS_FORBIDDEN_STRINGS is unset; forbidden-string checks skipped' -- seen as 6 skips in every local and CI run.
- Controller run 2026-10-01 with the real match file: `tests/test_forbidden_strings.py tests/sitebuild` 765 passed, 0 skipped.

## How to pick it up
1. Read `.github/workflows/ci.yml` and `tests/_forbidden_strings.py`.
2. Move the secret-writing step before pytest and run pytest with `FITDOCS_FORBIDDEN_STRINGS="$RUNNER_TEMP/forbidden-strings.txt"` (fork PRs without the secret must still fail closed or be handled as `ci.yml` already does for check_artifacts).
3. Update `tests/test_ci_workflow.py` pins for the new step order; check `docs.yml`'s byte-identical secret-step test still holds.
