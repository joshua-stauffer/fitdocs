---
id: 2026-10-02-ci-tests-only-python-3-11-of-the-supported-range
title: CI runs the suite on Python 3.11 only while the package declares >=3.11 and classifies 3.11-3.13, so interpreter-dependent behaviour is never tested where users run it
status: done
importance: medium
importance_why: Version-dependent stdlib behaviour has already bitten this repo's tests twice (Path.stat call counts, pathlib's attribute set); a published package that claims 3.12 and 3.13 has never had its suite run on them in CI.
effort: S
kind: gap
area: distribution, .github/workflows/ci.yml, pyproject.toml
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "do: add a Python-version matrix (3.11, 3.12, 3.13) to the test job in .github/workflows/ci.yml (keep the build/check-artifacts steps on one version), fix whatever goes red, and close or narrow .kiro/queue/2026-10-01-identity-guard-filesystem-attribute-set-varies-with-the-python-version.md accordingly"
context:
  - .github/workflows/ci.yml
  - pyproject.toml
  - tests/connectors/test_folder.py
  - tests/identity/test_boundary.py
  - .kiro/queue/2026-10-01-identity-guard-filesystem-attribute-set-varies-with-the-python-version.md
blocked_by: []
---

## What
`.github/workflows/ci.yml:50` runs `uv python install 3.11` and the whole job
uses that one interpreter. `pyproject.toml:6` declares
`requires-python = ">=3.11"` and `:18-20` list the 3.11, 3.12 and 3.13
classifiers. No CI job runs the suite on 3.12 or 3.13.

## Why it matters
Tests in this repo have already depended on interpreter details:
- `tests/connectors/test_folder.py:799-805` records that counting
  `Path.stat` calls is "fragile across Python versions -- `Path.is_file()`
  calls `stat()` on 3.11 but not on 3.14"; the connectors task 4.2 reviewer
  found that assumption in a test before it was rewritten. A CI that only
  runs 3.11 could not have caught it.
- `2026-10-01-identity-guard-filesystem-attribute-set-varies-with-the-python-version`
  documents a guard whose strictness changes per interpreter.
A user on 3.13 (classified as supported) is running a combination no CI run
has exercised; a failure there reaches a published release.

## Evidence
- `.github/workflows/ci.yml:50`, `pyproject.toml:6`, `:18-20`, read at
  `ad985b3` (`grep -n "python" .github/workflows/ci.yml`).
- The Path.stat case: the comment cited above is the current state; the
  original failing assumption was reported by the task 4.2 reviewer subagent
  and is not reproducible at this pin (it was fixed).

## How to pick it up
1. Read `.github/workflows/ci.yml` end to end -- the build and
   `check_artifacts` steps should run once, the test steps per version.
2. Add `strategy.matrix.python: ["3.11", "3.12", "3.13"]` and use it in the
   `uv python install` step; keep mypy's `python_version = "3.11"`
   (`pyproject.toml:86`) as the floor.
3. Run the suite locally on 3.13 (`uv run --python 3.13 pytest`) before
   pushing to see what reds; fix or mark interpreter-specific tests with a
   reason.
4. Done when CI is green on all three; then revisit the identity-guard item
   in `context` (its option 2 is this change).

## Resolution (2026-10-18)

Fixed on main at accccba (chore/q-ci-matrix; three Opus review rounds, final APPROVED; branch CI green on
3.11, 3.12 and 3.13). ci.yml keeps `gates` on 3.11 (lint, mypy, build, check-artifacts, armed suite)
and adds `supported-pythons` (3.12, 3.13; tests only; UV_PYTHON set because .python-version pins
3.11; interpreter asserted). Reds it surfaced and fixed: hero-chart boxcar_smooth depended on 3.12's
compensated float sum() (now explicit left-to-right, goldens unchanged); identity/plans/sitebuild guard
fixtures depended on interpreter-incidental stdlib attributes and PEP 695 AST nodes.
release.yml's gates job is still 3.11-only and unarmed: queued as
.kiro/queue/2026-10-18-release-gates-job-3-11-only-and-unarmed.md. Other builtin float sum() sites:
.kiro/queue/2026-10-18-float-sum-interpreter-dependence.md.
