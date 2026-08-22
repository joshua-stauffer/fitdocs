---
id: 2026-07-26-loadcalculator-stubs-outside-mypy-scope-have-drifted
title: Five LoadCalculator stubs outside mypy's scope have already drifted from the Protocol
status: done
importance: medium
importance_why: The drift this guard exists to catch is already present — six stubs do not structurally satisfy LoadCalculator today — and threshold-load and load-channels both change that signature next.
effort: S
kind: gap
area: tooling, tests/load/, pyproject.toml
created: 2026-07-26
surfaced_by: /kiro-queue sweep — implementing 2026-07-26-tests-not-type-checked
pinned_at: dc10200
resume_command: "do: fix the six LoadCalculator conformance errors in tests/load/test_engine.py and tests/load/test_arbitration_e2e.py (all `required_athlete_fields -> tuple[object, ...]` where the Protocol is covariant in `tuple[AthleteField, ...]`), then add those modules to [tool.mypy] files in pyproject.toml so they cannot drift again [queue: .kiro/queue/2026-07-26-loadcalculator-stubs-outside-mypy-scope-have-drifted.md]"
context:
  - pyproject.toml
  - tests/load/test_engine.py
  - tests/load/test_arbitration_e2e.py
  - tests/load/test_registry.py
  - src/fitdocs/load/types.py
blocked_by: []
---

## What

`dc10200` extended mypy's scope to `src` plus the five test modules that
*claimed* to be type-checked, at a measured cost of zero errors. That was the
decision taken, and it is correct as far as it goes.

It is a **partial perimeter**. Ten test modules hold a `LoadCalculator`-shaped
stub; five are now guarded and five are not:

| Guarded (in `[tool.mypy] files`) | Unguarded |
|---|---|
| `tests/load/conftest.py` | `tests/load/test_engine.py` |
| `tests/load/test_types.py` | `tests/load/test_arbitration_e2e.py` |
| `tests/load/test_arbitrate.py` | `tests/load/test_registry.py` |
| `tests/test_contributing_calculators_doc.py` | `tests/test_cli.py` |
| `tests/test_docs_guarantees.py` | `tests/test_plugin_regression.py` |

**And the drift is not hypothetical — it has already happened.** Adding the
five unguarded modules to the scope reports 15 errors in 5 files, of which
**six are genuine `LoadCalculator` conformance failures**: those stubs do not
structurally satisfy the Protocol they are registered against.

The defect is the same one this sweep just fixed in `docs/plugins.md`:

```
Argument 1 to "register" has incompatible type "_AltRunCalculator";
expected "LoadCalculator"
  Expected: def required_athlete_fields(self) -> tuple[AthleteField, ...]
  Got:      def required_athlete_fields(self) -> tuple[object, ...]
```

Return types are **covariant**, so `tuple[object, ...]` does not satisfy
`tuple[AthleteField, ...]`. (Note the sibling annotations `activity: object`,
`profile: object` etc. on the same stubs are *legal* — parameter types are
contravariant, so `object` always conforms. Only the return is wrong.)

## Why it matters

This is precisely the failure the parent item was opened to prevent, observed
rather than predicted. `training-load` task 3.3 took `compute` from four
parameters to five and every stub had to be moved by hand; the suite stayed
green throughout because nothing type-checked them. `threshold-load` and
`load-channels` both extend this surface next, so the same hand-migration is
about to happen again — across five modules that still have no static check.

The stakes are bounded: these are test stubs, not shipped code, and the suite
passes. What is lost is the guarantee. A stub that no longer matches the
contract still exercises the engine through the registry at runtime, so the
tests keep passing while silently testing against a shape no real plugin could
have.

## Evidence

Verified at `dc10200` in the sweep worktree:

```
$ grep -rln "context: LoadContext" tests/ | wc -l
10                                    # modules holding a stub

$ uv run mypy                          # the shipped scope
Success: no issues found in 63 source files

$ uv run mypy src <the five guarded> <the five unguarded>
Found 15 errors in 5 files (checked 68 source files)
```

The six conformance errors, by stub:

- `tests/load/test_engine.py` — `_AltRunCalculator` (×3 registration sites),
  `_ContextEchoCalculator` (×2), `_NonCoveringForcedCalculator` (×1)
- `tests/load/test_engine.py:965` is the representative declaration:
  `def required_athlete_fields(self) -> tuple[object, ...]:`

The other nine errors are unrelated to `LoadCalculator` and are what make this
`S` rather than trivial — they need judgement, not a find-and-replace:

- `_DummyTiles` / `_ServingTiles` vs `TileSource` (`test_cli.py`,
  `test_engine.py`, `test_arbitration_e2e.py`) — the same covariance question
  for a different Protocol
- `Module "fitdocs.load.engine" does not explicitly export attribute
  "load_settings_document"` — a real `__all__` question, not a test defect
- one `Non-overlapping equality check` in `tests/load/test_render.py`
- one `Unused "type: ignore"`, and two `garmin_fit_sdk` missing-stub warnings
  from `tests/fixtures/builder.py`

## How to pick it up

1. Reproduce the count with the command in Evidence, so you are working from
   today's number rather than this one.
2. Fix the six `required_athlete_fields` returns first — they are mechanical
   (`tuple[object, ...]` → `tuple[AthleteField, ...]`, importing
   `AthleteField`) and they are the ones that matter, because they are the
   contract this guard exists to protect.
3. Then triage the remaining nine. The `TileSource` ones are the same
   covariance shape and probably the same fix. The `load_settings_document`
   export error is a genuine question for whoever owns `engine.py`'s `__all__`
   — do not silence it with an ignore without deciding.
4. Add each module to `[tool.mypy] files` in `pyproject.toml` **as you fix
   it**, so the scope only ever contains modules that pass. Adding them all
   first makes the DoD red and blocks every other change.
5. Verify the guard on each newly added module the way `dc10200` did: change a
   stub's `context: LoadContext` to `context: str` and confirm `uv run mypy`
   names it; revert. Do not use `object` for this mutation — it is
   contravariantly legal and will not fail.

Done means: every module holding a `LoadCalculator` stub is in mypy's scope,
`uv run mypy` is green, and a signature change in `src/fitdocs/load/types.py`
reddens every stub that did not move with it.

## Open questions

- Is full `tests/` scope now worth reconsidering? The original measurement was
  277 errors in 36 files, which was rejected as too expensive. Closing these
  five modules removes the highest-value subset; whether the remaining ~31
  files are worth it is a separate call, and the answer may now be "no, and
  that is fine" — which is worth writing down so it stops being re-derived.


## Resolution

**Done 2026-07-26** — `5a8c28d`, branch `chore/queue-top-ten`.

Reproduced at 15 errors in 5 files, then fixed all 15 -- none silenced:
six `required_athlete_fields` returns, three `TileSource` fakes (the same
covariance shape, plus one unused `type: ignore` masking a non-iterable
annotation), the `load_settings_document` implicit re-export, a non-overlapping
equality in `test_render.py`, and the `garmin_fit_sdk` stubs.

The `load_settings_document` export question was decided rather than silenced:
NOT added to `engine.__all__`, because the name belongs to `fitdocs.settings`
and the engine only imports it. The test takes the original from the defining
module; its monkeypatch still targets the engine's own binding, which is the
point of the test.

All five modules added to `[tool.mypy] files`, and the guard verified **per
module** -- mutating a stub's `context: LoadContext` to `context: str` reddens
mypy in each (14/12/94/12/6 errors). The `object` trap the item warns about is
recorded next to the file list.

Open question -- whether full `tests/` scope is now worth it -- deliberately NOT
answered here; it remains open.
