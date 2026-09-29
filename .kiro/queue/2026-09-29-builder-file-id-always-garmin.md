---
id: 2026-09-29-builder-file-id-always-garmin
title: Every builder fixture declares file_id manufacturer garmin, including the HealthFit-shaped developer-field and re-export fixtures, which activity-identity therefore classifies as originals
status: open
importance: low
importance_why: Tests stay correct, but a fixture named for a HealthFit re-export exercises the original path, so a reader (or a future test) can believe the phone-copy path is covered where it is not.
effort: S
kind: chore
area: fit-ingest, activity-identity, running-dynamics, tests/fixtures/builder.py
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, activity-identity writer)
pinned_at: f500dc1
resume_command: "do: once activity-identity and running-dynamics have landed (they add keyword-only manufacturer parameters to builder._file_id and _device_info), pass manufacturer=development to the HealthFit-shaped builder fixtures (session_dev_fields*, reexport_a/b), re-run the suite, and for every test whose expectation moves decide whether it meant original or phone_copy; or, if that churn is not worth it, reword the fixtures' docstrings to say they are Garmin-manufactured and close this item"
context:
  - tests/fixtures/builder.py
  - .kiro/specs/activity-identity/design.md
  - .kiro/specs/activity-identity/requirements.md
blocked_by: [activity-identity, running-dynamics]
---

## What
`_file_id` hard-codes `"manufacturer": "garmin"` and every builder fixture
calls it, including `_encode_run_with_developer_fields`, which produces the
HealthFit-shaped `session_dev_fields_fit_bytes`,
`session_dev_fields_declared_scale_fit_bytes` and the
`reexport_a_fit_bytes` / `reexport_b_fit_bytes` pair (all carrying HealthFit's
`SESSION UUID`). A real HealthFit copy records `development`. Under
activity-identity Req 2.3 any manufacturer other than `development`
classifies `original`, so these fixtures are originals, not phone copies.
activity-identity adds realistic species in `tests/fixtures/identity.py` and
deliberately leaves the existing builder bytes unchanged.

## Why it matters
Low. The mismatch misleads rather than breaks: the fixture names promise a
shape the bytes do not have.

## Evidence
- `tests/fixtures/builder.py:146-154` (`_file_id`, manufacturer `garmin` at
  `:150`); `:162` (`_device_info`, also `garmin`); `:1024`
  (`_encode_run_with_developer_fields` calls `_file_id(serial)`).
- `.kiro/specs/activity-identity/requirements.md:134-135` (Req 2.2 phone
  copy = `development` + `SESSION UUID`; Req 2.3 any other manufacturer is
  original).
- `.kiro/specs/activity-identity/design.md` ~:195-200 and ~:522-526 (the
  shared builder seam; "existing callers keep their bytes").

## How to pick it up
1. Read `tests/fixtures/identity.py` (added by activity-identity) to see
   whether it already covers every HealthFit shape the old fixtures claim.
2. Try the one-argument change on the four fixtures and list which tests
   move (goldens, hashes, identity outcomes).
3. Pick fix-or-relabel with that list in hand; done when no fixture name or
   docstring claims a shape its bytes do not have.
