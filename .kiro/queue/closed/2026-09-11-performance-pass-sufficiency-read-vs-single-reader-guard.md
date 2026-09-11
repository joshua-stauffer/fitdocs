---
id: 2026-09-11-performance-pass-sufficiency-read-vs-single-reader-guard
title: performance-benchmarks' PassEngine cannot call load_load_settings without breaking training-load's single-reader guard
status: done
importance: high
importance_why: Blocks task 4.2 (and any later task) from reading `[load].sufficiency` the way design.md prescribes; will recur identically for whoever lands 4.2 unless resolved first.
effort: S
kind: inconsistency
area: performance-benchmarks, training-load
created: 2026-09-11
surfaced_by: /kiro-impl performance-benchmarks 4.1
pinned_at: 9ac4e2a
resume_command: "/kiro-impl performance-benchmarks 4.2 [queue: .kiro/queue/2026-09-11-performance-pass-sufficiency-read-vs-single-reader-guard.md] Resolve how PassEngine obtains LoadSettings.sufficiency without a second load_load_settings caller"
context:
  - .kiro/specs/performance-benchmarks/design.md (PassEngine, Req 9.7: "reads the stream-sufficiency settings from the existing training-load configuration")
  - .kiro/specs/performance-benchmarks/tasks.md (task 4.1, task 4.2)
  - src/fitdocs/performance/engine.py
  - tests/load/test_settings.py (test_load_load_settings_is_called_from_exactly_one_module, and its "behavioral companion" test_load_load_settings_is_called_the_documented_number_of_times_per_command)
  - src/fitdocs/load/settings.py
blocked_by: []
---

## What
`performance-benchmarks`' design (`design.md` § PassEngine, "Responsibilities
& Constraints", Req 9.7) directs the derivation pass to obtain
`LoadSettings.sufficiency` "from the existing training-load configuration"
(`load_load_settings`). But `tests/load/test_settings.py` pins, for
`training-load` (its Req 14.1), that `load_load_settings` is called from
**exactly one module in shipped source: `load/engine.py`** — and that guard
is watertight: a plain AST walk over every call-site spelling
(`test_load_load_settings_is_called_from_exactly_one_module`) plus a
behavioral spy that instruments the reader itself across every documented CLI
command (`test_load_load_settings_is_called_the_documented_number_of_times_per_command`,
described in that file as closing every aliasing/indirection technique the
AST walk alone would miss). Any call to `load_load_settings` from
`src/fitdocs/performance/engine.py` reddens the first guard immediately; the
second would catch it too if the CLI command were wired up (task 4.4).

Verified directly: adding `from fitdocs.load.settings import
load_load_settings` plus a call site to `src/fitdocs/performance/engine.py`
and running `uv run pytest -q` reddens
`tests/load/test_settings.py::test_load_load_settings_is_called_from_exactly_one_module`
with `load_load_settings is called from ['load/engine.py',
'performance/engine.py'], expected exactly ['load/engine.py']`, while the
rest of the 3554-test suite stays green.

## Why it matters
Task 4.1's engine skeleton (this session) worked around this by deferring
the sufficiency-settings read entirely — `derive_benchmarks` in task 4.1
reads no configuration at all, since 4.1's own "Observable" line doesn't
require it even though its prose bullet does. Task 4.2 has no such room: its
whole point is to thread `sufficiency` into `performance.derive.derive`
(`derive(activity, tag, on=..., document=..., sufficiency=...)`), so it
*must* obtain a `SufficiencySettings` instance from somewhere, and the
literal reading of design.md points straight at the same blocked call.
Without a decision here, task 4.2's implementer will either hit the same
regression, invent a second private reader (explicitly forbidden — "no
second reader of `[load]`"), or silently duplicate `[load.sufficiency]`
parsing logic (also forbidden by the hard rules in tasks.md).

## Evidence
- `tests/load/test_settings.py:1550` — the AST-walk guard, `assert callers ==
  {Path("load/engine.py")}`.
- `tests/load/test_settings.py:1858` onward — the behavioral companion
  ("Package-wide behavioral companion (task 6.4 round 2, Req 14.1)").
- `.kiro/specs/performance-benchmarks/design.md` § PassEngine,
  "Responsibilities & Constraints": "Reads each page exactly once..." and the
  Dependencies list naming `fitdocs.load.settings` + `fitdocs.settings` (P1).
- `.kiro/specs/performance-benchmarks/tasks.md` task 4.1 bullet: "read the
  stream-sufficiency settings from the existing training-load configuration
  and add no new key or table."
- `src/fitdocs/performance/engine.py` module docstring (added this session)
  documents the deferral and points here.

## How to pick it up
1. Re-run the reproduction: temporarily add a `load_load_settings` call to
   `src/fitdocs/performance/engine.py` and run `uv run pytest -q
   tests/load/test_settings.py` to confirm the guard still fires as
   described (guards can drift).
2. Decide the resolution — most likely one of:
   - Amend `training-load`'s single-reader guard (an Existing Spec Update,
     the same shape as the `athlete-benchmarks` amendment already landed in
     this plan) to accept `performance/engine.py` as a second, sanctioned
     caller, updating both the AST-walk assertion and the behavioral
     companion's expected call sites/counts.
   - Or: have `fitdocs.load.settings` expose a second, explicitly-sanctioned
     entry point for a *sibling pass* to obtain `LoadSettings` without
     widening the single-reader guard's definition of "the load table is
     parsed from exactly one place" (the reader itself, not the call site
     count, may be what Req 14.1 actually needs to protect — worth rereading
     `training-load`'s own Req 14.1 text before choosing).
3. Whichever path is chosen, update `design.md`'s PassEngine section and
   task 4.2's bullets to say so explicitly, so the guard and the design agree
   before task 4.2 is implemented.

## Resolution

Ruling (recorded in `tasks.md` § Implementation Notes `(4.1 -> 4.2)`),
applied by task 4.2: the first option under "How to pick it up" above. Req
14.1's guarantee is that `[load]` is parsed from exactly one *reader*
(`load_load_settings`), not that the reader has exactly one *call site*.
`src/fitdocs/performance/engine.py`'s `derive_benchmarks` is now a second,
sanctioned caller alongside `load/engine.py`'s `apply_load`, calling that
same single reader once per invocation (never once per document) rather than
opening a second reader or duplicating `[load.sufficiency]` parsing logic.

`tests/load/test_settings.py::test_load_load_settings_is_called_from_exactly_one_module`
is widened accordingly: its expected caller set is now
`{Path("load/engine.py"), Path("performance/engine.py")}`, and its docstring
now states the "one reader, two passes" framing directly (the reader itself
stays singular; two passes now consume it, training-load Req 14.1). The
behavioral companion
(`test_load_load_settings_is_called_the_documented_number_of_times_per_command`)
is untouched by this task -- `performance/engine.py` is not yet reachable
from any CLI command (that lands in task 4.4), so it does not yet appear in
that test's per-command call counts.

## Closed 2026-09-11 (performance-benchmarks 4.2)

Ruling applied: training-load Req 14.1 pins one READER of `[load]`, not one
caller. `src/fitdocs/performance/engine.py` calls `load_load_settings` once
per invocation before the document loop (pinned by
`tests/performance/test_engine.py::test_sufficiency_settings_are_read_once_and_threaded_into_derive`,
which reds when the call moves inside the loop or when a default
`SufficiencySettings()` is threaded instead), and
`tests/load/test_settings.py::test_load_load_settings_is_called_from_exactly_one_module`
now expects exactly `{load/engine.py, performance/engine.py}` (reds in both
directions: removing the pass's call, or adding a guarded third caller in
`load/docedit.py`). The behavioural per-command companion gains its
`derive-benchmarks` row when task 4.4 wires the command.
