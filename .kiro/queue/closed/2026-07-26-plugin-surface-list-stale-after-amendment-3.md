---
id: 2026-07-26-plugin-surface-list-stale-after-amendment-3
title: The published plugin surface list omits six exported names, and plugin-api has no open task to fix its copy
status: open
importance: medium
importance_why: A plugin author reading docs/plugins.md cannot discover LoadContext — the parameter `compute` now requires — so the documented surface is not sufficient to write a working calculator against.
effort: S
kind: inconsistency
area: plugin-api, training-load, docs/plugins.md
created: 2026-07-26
surfaced_by: /kiro-impl training-load (task 5.2, review and confirmatory review)
pinned_at: c3d2201
resume_command: "do: docs/plugins.md's surface list, prose, and worked example are already reconciled and mechanically guarded (queue sweep, 2026-07-26) — the only remaining work is plugin-api task 4.4, reconciling .kiro/specs/plugin-api/design.md's own public-surface enumeration (~line 806) and its RECORDED FOLLOW-UP note (design.md:815-837) against the shipped training-load contract; see .kiro/specs/plugin-api/tasks.md task 4.4 for the full scope"
context:
  - docs/plugins.md
  - src/fitdocs/load/__init__.py
  - .kiro/specs/plugin-api/design.md
  - .kiro/specs/plugin-api/tasks.md
  - .kiro/specs/training-load/tasks.md
blocked_by: []
---

## What

Two copies of the published plugin-author surface are stale against the contract
Amendment 3 shipped, in different ways.

**`docs/plugins.md` (shipped documentation).** Its `From fitdocs.load` block
omits **six** names that are really exported. Measured at `fe5d5f7` by comparing
the doc against the live `__all__`:

```
DEFAULT_LOAD_SETTINGS, LoadContext, LoadSettings, LoadSettingsError,
registry, supports_activity
```

**`.kiro/specs/plugin-api/design.md:806`** carries its own copy of the surface
list with the same class of staleness, and `plugin-api` has **no open task to
land a correction** — all 11 leaf tasks are `[x]`, and its design note at
`:815-817` says "Not a re-spec: this spec's requirements, tasks and approvals
are unchanged."

Task 5.2 corrected the two *defects* in `docs/plugins.md` — a false
compatibility promise, and `NotConfirmed` in the surface list resolving nowhere
— but the wider list refresh was explicitly out of that task's text.

## Why it matters

`medium`, and the reason is specific rather than tidiness.

`LoadContext` is the parameter `LoadCalculator.compute` now **requires**. An
author working only from `docs/plugins.md` cannot discover it: the surface list
does not name it, and the surrounding prose predates it. They will write a
four-parameter `compute` — exactly the shape the installed plugin fixture was
left in, which task 4.1 had to repair. The documented surface is not sufficient
to write a working calculator against.

`supports_activity` is the same story one level down: the guide teaches that a
calculator may optionally define `supports`, but the module-level function the
engine actually asks through is absent from the list.

The `plugin-api` copy matters less directly (it is a spec file, not shipped),
but it is the canonical list that a future surface change will be diffed
against, and it has no vehicle to be corrected.

## Evidence

Verified in this run at `fe5d5f7` (branch `impl/training-load`):

- Live comparison against the real export list:
  ```
  $ uv run python -c "
  import fitdocs.load as L
  doc = open('docs/plugins.md').read()
  print([n for n in L.__all__ if n not in doc])"
  ['DEFAULT_LOAD_SETTINGS', 'LoadContext', 'LoadSettings', 'LoadSettingsError',
   'registry', 'supports_activity']
  ```
- `grep -c "^- \[ \] [0-9]\+\.[0-9]" .kiro/specs/plugin-api/tasks.md` → **0**
  open leaf tasks; `grep -c "^- \[.\] [0-9]\+\.[0-9]"` → 11 total. The four
  unchecked entries are section headers, not leaves.
- `.kiro/specs/plugin-api/design.md:815-834` records the obligation but
  explicitly declines to reopen the spec.

Note `registry` in that list is the submodule, not a contract symbol — decide
deliberately whether the guide should name it, rather than pasting all six.

## How to pick it up

1. **`docs/plugins.md` first** — it is shipped and is what an author reads. Add
   the missing contract names to the `From fitdocs.load` block. Refresh the
   prose around `compute` for the `LoadContext` parameter, and the `supports`
   discussion for `supports_activity`. `docs/contributing-calculators.md` was
   rewritten against the shipped contract by task 5.1 and its worked example is
   machine-checked — use it as the reference for what is true.
2. Consider whether the surface list should be **generated or asserted** rather
   than hand-maintained. `tests/test_public_api.py` already pins `__all__`; a
   test asserting every name in the doc's list imports, and that no exported
   contract name is missing from it, would prevent the third occurrence of this.
   That is the durable fix and is cheap.
3. **`plugin-api` needs an open task before its copy can be corrected.** Do not
   edit `plugin-api/design.md` from another spec's run — add a task to
   `plugin-api/tasks.md` covering the surface-list reconciliation, then land it
   there. This is the step the existing four recordings all skip, which is why
   the obligation has survived three sessions.
4. Done looks like: `docs/plugins.md`'s list agrees with `fitdocs.load.__all__`
   modulo a deliberate decision about `registry`; the `compute` prose names
   `LoadContext`; `plugin-api`'s copy matches; and ideally a test makes the
   agreement mechanical.

Do this before `threshold-load` starts — it is the first spec that will write a
real calculator from this page.


---

## Update 2026-07-26 (training-load task 6.4 feature validation, at 3121bb6)

**A second, different file carries the same staleness, and this one ships to
users.** `docs/plugins.md`'s `From fitdocs.load:` list (~lines 236-239) omits
**seven** names the surface actually exports: `LoadContext`, `LoadSettings`,
`DEFAULT_LOAD_SETTINGS`, `LoadSettingsError`, `NonSelectedValue`, `QualityFlag`
and `supports_activity`. This item's original evidence names
`plugin-api/design.md:806` — a spec file — so the two are not duplicates and
both need the same edit.

Task 6.4 added `tests/test_docs_guarantees.py::test_every_name_in_the_plugins_doc_public_surface_list_actually_imports`,
which pins one direction only: every **listed** name must import. Nothing
asserts **completeness** — that every exported name is listed — which is why
the seven omissions are invisible to the suite. Closing this item should add
the reverse assertion, at which point the list cannot drift again in either
direction.

## Update 2026-07-26 (queue sweep)

**The `docs/plugins.md` half is done; the `design.md` half is not — status
stays `open`, now owned by `plugin-api` task 4.4.**

What landed (commit `d7f197f`, this queue sweep's own verification at the
current worktree state):

- `docs/plugins.md`'s `From fitdocs.load:` list is complete both ways.
  Measured directly against the live export list:
  `[n for n in fitdocs.load.__all__ if n not in open('docs/plugins.md').read()]`
  now returns `[]` — no name in either direction is missing.
- `tests/test_docs_guarantees.py` gained the reverse assertion this update's
  prior text asked for:
  `test_every_fitdocs_load_export_appears_in_the_plugins_doc_surface_list`
  (bidirectional guard, alongside the pre-existing
  `test_every_name_in_the_plugins_doc_public_surface_list_actually_imports`),
  plus a mechanically-checked worked example
  (`test_plugins_doc_worked_example_type_checks_against_the_shipped_contract`)
  that type-checks the `compute` signature itself under `mypy --strict`
  against `LoadCalculator`, so the signature (not just the name list) cannot
  drift silently either.
- `plugin-api/tasks.md` gained the open leaf task this update's prior text
  said was missing: **4.4**, "Reconcile the design's public-surface
  enumeration against the shipped `training-load` contract" — the vehicle
  this item's "How to pick it up" step 3 called for.

What remains, now owned by task 4.4 rather than this queue item alone:
`.kiro/specs/plugin-api/design.md`'s own copy of the surface enumeration
(~line 806) and its **RECORDED FOLLOW-UP (2026-07-25, cross-spec review)**
note (`design.md:815-837`) are both still the pre-`training-load` list —
`design.md` is out of scope for every task and every spec file this queue
sweep is authorized to touch, so it is untouched here. Task 4.4 is the one
task in the codebase permitted to edit it.

Corrections to this item's own prior Evidence text, which the fixes above
have made stale:

- "6 missing… then 7, then 8 measured today" no longer describes the current
  state of `docs/plugins.md` — the count is 0 today, verified above.
- "Nothing asserts completeness" is no longer true of `docs/plugins.md`
  specifically; it remains true of `design.md`'s copy, which task 4.4 has not
  yet touched.

`resume_command` above still names `docs/plugins.md` work that is already
done; it should be read as superseded. The only remaining work this item
tracks is `plugin-api` task 4.4's `design.md` half — see
`.kiro/specs/plugin-api/tasks.md` (task 4.4) for its own resume path.

## Update 2026-07-27 (plugin-api task 4.4, not yet merged)

**The `design.md` half is done, committed `6de9b13` on branch
`impl/plugin-api-surface` (worktree `../fitdocs-plugin-surface`) — status
stays `open` until that branch merges to `main`, at which point this item
should move to `closed/`.**

`design.md`'s Packaging + PublicApi enumeration (~line 806) is reconciled
against the live `fitdocs.load.__all__` / `fitdocs.__all__`: `NotConfirmed`
renamed to `NotComputed`, and `LoadContext`, `LoadSettings`,
`LoadSettingsError`, `DEFAULT_LOAD_SETTINGS`, `NonSelectedValue`,
`QualityFlag`, `supports_activity` added. `registry` is deliberately
excluded from the depend-on list (re-exported submodule, not a contract
symbol), matching `docs/plugins.md`'s own stated decision on the same name.
Verified with a mechanical diff of the design's enumeration against
`fitdocs.__all__` and `fitdocs.load.__all__` (minus `registry`): empty in
both directions. The design's own 2026-07-25 RECORDED FOLLOW-UP note is
replaced with a RESOLVED note. All 12 leaf tasks in
`.kiro/specs/plugin-api/tasks.md` are now `[x]`; no approval flag changed
(not a re-spec). Once `impl/plugin-api-surface` merges, this item is fully
closed and should move to `.kiro/queue/closed/`.
