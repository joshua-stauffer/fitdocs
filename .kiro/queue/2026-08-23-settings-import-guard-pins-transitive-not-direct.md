---
id: 2026-08-23-settings-import-guard-pins-transitive-not-direct
title: The settings import guard pins transitive presence, stronger than Req 14.7 asks
status: open
importance: low
importance_why: Downgraded 2026-09-18 — activity-qa-flags task 3.1 hit exactly the predicted event (a sanctioned fitdocs.load.* import added to settings.py) and rewrote the guard into a differential exclusivity check that survived two adversarial review rounds and five targeted attacks; the practical signposting problem this item raised is resolved for the case that actually occurred. What remains is a documentation/ownership question, not a live guard defect.
effort: S
kind: inconsistency
area: load-channels, training-load, activity-qa-flags, tests/load/test_settings.py
created: 2026-08-23
surfaced_by: /kiro-impl load-channels task 2.3 adversarial review
pinned_at: 53ece33
resume_command: "do: decide formal ownership of test_settings_module_leaks_no_dynamic_import_of_load_types (introduced by load-channels ae0790d, rewritten by activity-qa-flags task 3.1 fd9bb7a) and record it in one spec's design.md so a third spec doesn't rediscover the same guard cold"
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

## Update — 2026-09-18 (activity-qa-flags task 3.1 + feature-level validation)

The predicted event happened: `activity-qa-flags` task 3.1 landed
`qa/__init__.py`'s eager `from .flags import evaluate_flags`, which makes
`settings.py` reach `fitdocs.load.types` transitively — exactly the
sanctioned addition this item foresaw. The guard was rewritten in place
(`tests/load/test_settings.py`, commit range `fd9bb7a`..`f66e2b0` on
`impl/activity-qa-flags`, merged `d26b682`) into a **differential
exclusivity check**: exec the real `settings.py` off disk and assert
`fitdocs.load.types` lands (expected, via the sanctioned chain); exec the
same source with only that one sanctioned import line swapped for a
local, import-free stand-in and assert `fitdocs.load.types` is then
*absent*. This is a real answer to this item's open question — it
distinguishes "this specific sanctioned import causes the presence" from
"something else does" — not just a stronger transitive-presence check.

Verified independently by two review rounds: round 1 caught a **broken**
first attempt (assertions satisfied by the sanctioned chain regardless of
what `settings.py` actually did — a planted
`importlib.import_module("fitdocs.load.types")` stayed undetected); round
2's rebuild withstood 5 adversarial attacks including a trace-erasure
probe and 12 of the reviewer's own relative-import spellings.

**Ownership correction**: this item's `area` field, and
`activity-qa-flags`' own `tasks.md` Implementation Notes, both originally
attributed the guard to `training-load`/task 1.3. `git log -S
"test_settings_module_leaks_no_dynamic_import_of_load_types" --
tests/load/test_settings.py` shows it was introduced by **`load-channels`**
at `ae0790d` ("project the sufficiency settings from the shared load
table"); `activity-qa-flags` task 1.3 (`d807fc3`) never touched it — only
task 3.1 (`fd9bb7a`) rewrote it. `area` above corrected accordingly. The
formal-ownership question (which spec's design.md should record this
guard's contract) is what remains open; the guard itself is not currently
believed broken.
