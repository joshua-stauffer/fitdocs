---
id: 2026-10-01-fixture-builder-and-its-self-tests-are-outside-the-mypy-perimeter
title: tests/fixtures/builder.py and test_builder.py are not in the [tool.mypy] files list, although the identity fixtures built on them are, and test_builder.py has 12 strict errors
status: open
importance: low
importance_why: The builder is the fixture source for every identity and running-dynamics test and was extended by both specs, yet its typing is checked nowhere; the perimeter is opt-in, so this is a decision to record, not a regression.
effort: S
kind: chore
area: activity-identity, running-dynamics, pyproject.toml, tests/fixtures/builder.py, tests/fixtures/test_builder.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "do: decide whether tests/fixtures/builder.py and tests/fixtures/test_builder.py join [tool.mypy] files; if yes add them and fix the 12 errors in test_builder.py in the same change (pyproject.toml's comment forbids adding a module first), if no add a one-line comment above the list naming why they are excluded"
context:
  - pyproject.toml
  - tests/fixtures/builder.py
  - tests/fixtures/test_builder.py
  - .kiro/queue/2026-07-28-mypy-perimeter-membership-unguarded.md
blocked_by: []
---

## What
`pyproject.toml`'s `[tool.mypy] files` enumerates checked test modules one by
one. `tests/fixtures/identity.py` and `tests/fixtures/test_identity_fixtures.py`
(activity-identity) are in it; `tests/fixtures/builder.py` and
`tests/fixtures/test_builder.py`, which both specs also extended (activity-identity
tasks 1.1 and 1.2, running-dynamics 1.2), are not.

## Why it matters
The builder encodes the FIT bytes every identity, ingest and running-dynamics
test depends on; a wrong annotation or an unexported name there is invisible to
the type gate. The list's own comment says a module is added "and its errors
fixed in the same change", so the exclusion was probably a cost choice that was
never written down.

## Evidence
Measured at `fc5c06d`.
- `grep -n "test_builder\|fixtures" pyproject.toml` -> only `fixtures/identity.py`
  (`:163`) and `fixtures/test_identity_fixtures.py` (`:164`).
- `uv run mypy tests/fixtures/builder.py` -> `Success: no issues found in 1 source file`.
- `uv run mypy tests/fixtures/test_builder.py` -> `Found 12 errors in 1 file`:
  the `garmin_fit_sdk` import is untyped (`:16`, `import-untyped`), two
  `Returning Any from function declared to return "bool"` (`:23`, `:27`), eight
  `Module "tests.fixtures.builder" does not explicitly export attribute
  "BASE_TYPE"` (`:522, 664-669, 789-793`) and `Need type annotation for
  "_HELPER_RECORDS"` (`:671`). Most are older than activity-identity (the
  `BASE_TYPE` and `_HELPER_RECORDS` ones belong to running-dynamics' helper tests).

## How to pick it up
1. Decide: include both modules (add them to `files`, add a typed shim or a
   targeted `# type: ignore[import-untyped]` for `garmin_fit_sdk`, export
   `BASE_TYPE` explicitly, annotate `_HELPER_RECORDS`) or record the exclusion.
2. If including, run `uv run mypy src/` plus the configured perimeter command
   (`uv run mypy`) and see both green before committing.
3. The general guard against silently dropping an entry is the sibling item
   `2026-07-28-mypy-perimeter-membership-unguarded`; do not duplicate its work here.
