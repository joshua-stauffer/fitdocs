---
id: 2026-07-26-plugin-report-builtins-first-docstring
title: PluginReport.calculators still documents "built-ins first" after the last built-in was withdrawn
status: done
importance: low
importance_why: Documentation-only and user-invisible, but it is a published plugin-surface docstring that now describes an ordering the tool cannot produce, and it is the one such statement no task owns.
effort: S
kind: inconsistency
area: plugin-api, training-load, src/fitdocs/plugins.py
created: 2026-07-26
surfaced_by: /kiro-impl training-load (task 3.2 adversarial review)
pinned_at: c8034d5
resume_command: "do: correct the src/fitdocs/plugins.py:275 docstring for PluginReport.calculators so it no longer claims built-ins are registered first, and check the same file for other prose assuming a bundled calculator ships"
context:
  - src/fitdocs/plugins.py
  - src/fitdocs/load/__init__.py
  - .kiro/specs/training-load/requirements.md
  - .kiro/specs/training-load/tasks.md
blocked_by: []
---

## What

`src/fitdocs/plugins.py:275` documents the `PluginReport.calculators` field as:

> "Every registered calculator, in registration order (built-ins first)."

The parenthetical is false. training-load task 1.3 deleted the withdrawn
calculator — the only built-in the tool ever shipped — and Requirement 13.2
forbids shipping another: the load package's initializer must register nothing,
so a fresh interpreter reports an empty registry. There are no built-ins to come
first, and until `threshold-load` lands there is no bundled calculator at all.

The rest of the sentence is still correct: the tuple genuinely is in
registration order.

## Why it matters

Low stakes, deliberately filed as `low`. Nothing user-visible is wrong and no
behavior depends on it — `PluginReport` is a report type and the ordering claim
is descriptive, not enforced.

It is worth a file rather than nothing because this is the **published plugin
surface**. A plugin author reading it infers that bundled calculators exist and
take registration precedence over theirs, which is exactly the mental model
Requirement 13.2 removed. `plugin-api` already owes its surface a
compatibility-statement pass in training-load task 5.2; this is cheap to fold
into the same reading.

## Evidence

Verified in this run at `c8034d5` (branch `impl/training-load`), not taken on
the reviewer's word:

- `src/fitdocs/plugins.py:275` — `"""Every registered calculator, in
  registration order (built-ins first)."""`
- `src/fitdocs/load/__init__.py:10-12` — the package's own docstring already
  states the opposite: "Importing this package registers no built-in
  calculator: ``available()`` is empty until a downstream spec registers one."
  The two files contradict each other in shipped source.

**It is genuinely untracked.** `.kiro/specs/training-load/tasks.md` carries an
inventory headed "Prose falsified by task 1.3's deletion, deferred to the task
owning each file's boundary", which assigns `load/registry.py` to task 3.2
(landed as `c8034d5`) and `load/engine.py` to task 4.1. `plugins.py` appears
nowhere in that inventory, in any other `tasks.md` entry, or in
`.kiro/steering/roadmap.md` — checked before filing.

## How to pick it up

1. Open `src/fitdocs/plugins.py` at the `PluginReport` dataclass (~line 270).
   Drop the `(built-ins first)` clause; keep "in registration order", which is
   still true.
2. **A second instance is now located for you: `src/fitdocs/plugins.py:303-304`,
   inside `discover()`'s docstring** — *"Built-ins are already registered by the
   time this runs (`fitdocs.load` is imported at module load, which registers
   them -- Req 1.3), so they always occupy the first registry slots."* False
   under Req 13.2: `fitdocs.load.available()` is `()` on a real import, verified
   live at 3121bb6 on `impl/training-load`. Fix it in the same pass. Read the
   rest of `plugins.py` for further sibling assumptions — the
   module-level comment above the origin mapping (~line 280) and any
   `PluginInfo.origin` prose describing a built-in origin. Origin is assigned by
   *discovery channel*, so a test-registered calculator can still legitimately
   carry a built-in origin; do not delete the concept, only the claim that one
   ships.
3. Done looks like: no statement in `plugins.py` asserts a bundled calculator
   exists, `plugins.py` and `src/fitdocs/load/__init__.py:10-12` agree, and
   `uv run pytest && uv run ruff check . && uv run mypy src/` is green.

Fold into training-load task 5.2 if that lands first — it already reconciles
`plugin-api`'s published surface for the `NotConfirmed` → `NotComputed` rename,
and this is the same file family and the same reading.


## Resolution

**Done 2026-07-26** — `1727b0b`, branch `chore/queue-top-ten`.

Verified `fitdocs.load.available()` is `()`.

Five prose sites corrected: `PluginReport.calculators`' ordering parenthetical,
`discover()`'s "first slots" paragraph, `discover()`'s "built-ins are registered
regardless" clause, the module comment on local-channel ordering, and `BuiltIn`'s
own docstring. The origin *concept* is kept as the item instructed -- origin is
assigned by discovery channel, so a calculator registered outside the plugin
channels legitimately carries `BuiltIn`; only the claim that one ships was wrong.

The behaviour was already pinned by `test_fresh_interpreter_reports_the_registry_empty`;
what had no guard was the prose. Added
`test_plugins_module_prose_never_asserts_a_bundled_calculator_ships`, forbidding
the withdrawn wording verbatim with a positive control against reading the wrong
module. Three mutations, all red -- and it caught its own author first, when a
draft quoted the forbidden phrase while explaining it.
