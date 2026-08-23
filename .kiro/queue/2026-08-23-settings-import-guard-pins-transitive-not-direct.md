---
id: 2026-08-23-settings-import-guard-pins-transitive-not-direct
title: The settings import guard pins transitive presence, stronger than Req 14.7 asks
status: open
importance: medium
importance_why: It reds the day threshold-load or activity-qa-flags adds a sanctioned fitdocs.load.* import to settings.py — an event settings.py's own docstring promises — and the next spec owner will meet it as a mystery failure.
effort: S
kind: inconsistency
area: training-load, threshold-load, activity-qa-flags, tests/load/test_settings.py
created: 2026-08-23
surfaced_by: /kiro-impl load-channels task 2.3 adversarial review
pinned_at: 53ece33
resume_command: "do: decide whether Req 14.7 means no direct import or no transitive presence of fitdocs.load.types at settings-import time, then align tests/load/test_settings.py::test_settings_module_leaks_no_dynamic_import_of_load_types with the ruling"
context:
  - tests/load/test_settings.py
  - src/fitdocs/load/settings.py
  - src/fitdocs/load/registry.py
  - src/fitdocs/load/profile.py
blocked_by: []
---

## What

`test_settings_module_leaks_no_dynamic_import_of_load_types` execs
`settings.py` in a subprocess against stub packages carrying the real
`__path__`, then asserts `fitdocs.load.types` never landed in `sys.modules`.
That is *transitive* presence, not direct import.

Req 14.7, which belongs to `training-load`, says `settings.py` "imports nothing
from `fitdocs.load.types` **itself**". The guard is strictly stronger: because
`registry.py:33` and `profile.py:78` both import `fitdocs.load.types` at module
level, *any* real `fitdocs.load.*` import added to `settings.py` trips it.

The guard's docstring says "never landed in `sys.modules`", which matches what
it does — so nothing is false. The open question is which invariant is wanted.

## Why it matters

`settings.py`'s own docstring says sibling specs will add their own sub-table
projections, and the roadmap has two queued: `threshold-load` brings
`load/priority.py` and `activity-qa-flags` brings `load/qa/types.py`. The first
spec to import one of those from `settings.py` will red this guard with a
message about `fitdocs.load.types` — a module it never mentioned — and will have
to work out that the fix is to stub the new sibling in the subprocess script.

The failure message is accurate and the fix is one line, so this is a
signposting problem rather than a correctness one. It is cheap to settle now
and confusing to meet cold.

## Evidence

Measured at `53ece33` by the reviewer, not inferred:

- inserting `importlib.import_module("fitdocs.load.registry")` into
  `settings.py` — an unrelated, sanctioned-looking import — yields
  `AssertionError: leaked=['fitdocs.load.types']`
- the same for `fitdocs.load.profile`
- `src/fitdocs/load/registry.py:33` and `src/fitdocs/load/profile.py:78` each
  carry a module-level `from fitdocs.load.types import ...`

The guard is otherwise sound: across nine import spellings it and the static AST
walk have zero survivors between them, and neither subsumes the other.

## How to pick it up

1. Read Req 14.7 in `.kiro/specs/training-load/requirements.md` and the two
   guard tests in `tests/load/test_settings.py`.
2. Decide: does 14.7 forbid a direct import of `fitdocs.load.types`, or its
   presence in `sys.modules` after `settings.py` is imported?
3. If direct-only, narrow the runtime guard to inspect the import *record*
   rather than `sys.modules` membership, and keep the static walk as-is. If
   transitive, add a comment in `settings.py` warning that adding a sibling
   import requires stubbing it in the guard, and say so in Req 14.7.

Done looks like: the guard and the requirement agree, and a future sibling
import either passes or fails with a message naming the sibling.

## Open questions

- Is transitive presence actually harmful, or was Req 14.7 only ever about
  keeping `settings.py` free of the load layer's own value types?
- If transitive, should the guard enumerate sanctioned siblings so its failure
  message names the new one rather than `fitdocs.load.types`?
