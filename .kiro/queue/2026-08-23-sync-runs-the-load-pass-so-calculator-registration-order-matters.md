---
id: 2026-08-23-sync-runs-the-load-pass-so-calculator-registration-order-matters
title: fitdocs sync runs the load pass, so calculator registration order silently voids load tests
status: open
importance: medium
importance_why: A test registering a calculator before sync measures sync's own pass, not the load invocation under test — it produces a green, plausible, and meaningless result, and it cost two review rounds to diagnose.
effort: S
kind: gap
area: load-layer test fixtures, tests/load/conftest.py, tests/load/test_cli_load.py
created: 2026-08-23
surfaced_by: /kiro-impl load-channels task 2.3 adversarial review
pinned_at: 53ece33
resume_command: "do: give tests/load/conftest.py a field-free calculator fixture and document the register-after-sync ordering, then retire the three hand-rolled copies"
context:
  - src/fitdocs/cli.py
  - tests/load/conftest.py
  - tests/load/test_cli_load.py
  - tests/load/test_settings.py
blocked_by: []
---

## What

Two independent traps sit in the same place, and a test can hit both while
staying green.

First, `fitdocs sync` runs the load pass internally
(`cli.py::sync_command` → `_run_load_pass`). A test that registers a calculator
*before* syncing is measuring sync's own pass, not the later `fitdocs load`
invocation it means to exercise. The document comes back already computed, the
`load` run reports `Computed 0` and changes no bytes, and an assertion like
`assert after == before` passes for entirely the wrong reason.

Second, every calculator stub in `tests/load/conftest.py` declares a required
field, so under `--no-prompt` it lands in `MissingInputs` and computes nothing.
`tests/load/test_cli_load.py:551` carries a `_FieldFreeCalculator` that exists
solely to work around this, and its docstring says so.

Task 2.3 hit both. Three test modules now hand-roll their own field-free
calculator independently.

## Why it matters

The failure is invisible: the suite is green, the numbers look reasonable, and
the assertion appears to pin the thing it names. Task 2.3's write-suppression
assertion survived two review rounds looking vacuous, and the first diagnosis
(`MissingInputs` under `--no-prompt`) was true of one calculator but not the
actual cause. Only registering after sync revealed it.

Any future test asserting "the load pass wrote nothing" or "the load pass wrote
exactly this" is exposed to the same trap.

## Evidence

Measured at `53ece33`, both orderings run against the same fixture with a
field-free calculator:

- register **before** sync → `exit 0`, `Computed 0`, `changed files: []`
- register **after** sync → `exit 0`, `Computed 1`,
  `changed files: ['workouts/2021-09-08-run-0346.md']`

Reproduced independently by the reviewer with its own calculator, matching the
implementer's numbers exactly. `tests/load/test_cli_load.py:551` documents the
required-field problem in its own words; `:529` shows the alternative workaround
(`save_profile(data_root, profile.with_value(COMPUTING_FIELD, 5))`).

## How to pick it up

1. Read `cli.py::sync_command` and confirm the `_run_load_pass` call.
2. Read `tests/load/test_cli_load.py:529` and `:551` for the two existing
   workarounds, and `tests/load/test_settings.py`'s two-half integration test
   for the third.
3. Add a shared field-free calculator fixture to `tests/load/conftest.py` with a
   docstring stating the register-after-sync rule, then retire the copies.

Done looks like: one fixture, one documented rule, and no module hand-rolling
its own.

## Open questions

- Should `conftest.py`'s existing stubs keep their required fields at all, or is
  the required field incidental to what most of them are testing?
