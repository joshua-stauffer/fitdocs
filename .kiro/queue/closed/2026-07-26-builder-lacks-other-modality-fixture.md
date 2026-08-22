---
id: 2026-07-26-builder-lacks-other-modality-fixture
title: The shared FIT builder ships no Modality.OTHER fixture, so a test reaches into its private helpers
status: done
importance: medium
importance_why: The only reach into `builder`'s privates anywhere in the suite; a rename inside the shared fixture module now breaks an unrelated engine test, and the next spec needing a catch-all-modality document will copy the workaround.
effort: S
kind: gap
area: tests/fixtures, training-load
created: 2026-07-26
surfaced_by: /kiro-impl training-load (task 4.1, reviewer rounds 2 and 3)
pinned_at: 1b40c02
resume_command: "do: add a public Modality.OTHER document builder (a hike) to tests/fixtures/builder.py alongside run_fit_bytes/ride_fit_bytes, then repoint tests/load/test_engine.py's local _hike_fit_bytes/_hike_mesgs at it and delete the private-helper reach"
context:
  - tests/fixtures/builder.py
  - tests/load/test_engine.py
  - tests/load/conftest.py
  - .kiro/specs/training-load/tasks.md
blocked_by: []
---

## What

`tests/fixtures/builder.py` is the suite's shared FIT-bytes builder and ships
public helpers for the modalities the suite has needed so far — run and ride. It
ships **nothing for `Modality.OTHER`**.

Task 4.1 needed a `Modality.OTHER` document to pin Requirement 10.5: the
`DecliningCalculator` stub declares `Modality.OTHER`, refuses `Sport.ROWING`, and
supports `Sport.HIKE`, so the "answers yes, then `compute` still declines" path
is only reachable through a hike. With no public builder for one, the test module
constructed the document itself out of `builder`'s private helpers:

```
builder._file_id   builder._device_info   builder._activity
builder._MESG_SPORT   builder._MESG_RECORD   builder._MESG_SESSION
```

## Why it matters

`tests/load/test_engine.py` is the **only** file in the entire suite that reaches
into `builder`'s privates — `grep -rln 'builder\._' tests/` returns it and nothing
else. So this is a genuine convention break rather than an established pattern,
and it has two costs:

1. A rename or refactor inside `builder.py` — a shared fixture module every spec
   touches — now breaks an unrelated engine test with no signal at the point of
   change. The breakage would at least be loud and immediate rather than silent,
   which is why this is `medium` and not `high`.
2. `threshold-load` must declare `Modality.OTHER` to reach Walk and Hike, so it
   is the next spec that will need exactly this fixture. Without a public builder
   it will copy the private-helper reach, and the workaround becomes the pattern.

The task-4.1 reviewer explicitly adjudicated keeping the construction local as
the **correct** call for that task: the alternative was editing a suite-wide
shared module that maps to no component in 4.1's declared boundary, which is the
larger violation. This item is the deferred half of that adjudication, not a
complaint about it.

## Evidence

Verified in this run at `1b40c02` (branch `impl/training-load`):

- `grep -rln 'builder\._' tests/` → `tests/load/test_engine.py` only.
- `grep -o 'builder\._[a-zA-Z_]*' tests/load/test_engine.py | sort -u` → the six
  private names listed above.
- `grep -c 'hike\|HIKE\|Modality.OTHER' tests/fixtures/builder.py` → **0**: the
  shared module has no catch-all-modality fixture of any kind.
- The consuming tests are `test_calculator_declining_at_compute_reaches_unsupported_not_skipped`
  and its siblings in `tests/load/test_engine.py`, which the reviewer confirmed
  produce a real `workouts/2021-09-07-hike-1946.md` at `Modality.OTHER` reaching
  `DecliningCalculator.compute`.

## How to pick it up

1. Open `tests/fixtures/builder.py` and read how `run_fit_bytes` and
   `ride_fit_bytes` are assembled — the new helper should be a sibling of those,
   built from the same private pieces, not a new mechanism.
2. Add a public hike builder (`hike_fit_bytes`, or a modality parameter on an
   existing helper if that reads better against the current shape). Keep it
   **deterministic** — fixed constants, no clock — matching the existing helpers;
   the load suite asserts on generated document filenames, so a moving date would
   break it.
3. Repoint `tests/load/test_engine.py`'s local `_hike_fit_bytes` / `_hike_mesgs`
   at the new public helper and delete the private-helper reach.
4. Done looks like: `grep -rln 'builder\._' tests/` returns **nothing**, the
   hike-driven engine tests still pass, and `uv run pytest && uv run ruff check .
   && uv run mypy src/` is green.

Worth doing before `threshold-load` starts, since that spec needs the same
fixture and would otherwise duplicate the workaround.

## Resolution

**Done 2026-07-26** (queue sweep, merged to `main` at `e806c57`).

`ba96a44`. Worse than filed: three files reached into `builder`'s privates, not one — the workaround had already spread into training-load's group-6 e2e modules. `grep -rln 'builder\._' tests/` now returns nothing. Public `small_sport_fit_bytes` + `hike_fit_bytes`; pure refactor, verified modality-sensitive by mutation.
