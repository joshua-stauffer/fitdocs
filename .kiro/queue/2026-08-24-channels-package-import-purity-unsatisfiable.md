---
id: 2026-08-24-channels-package-import-purity-unsatisfiable
title: Task 4.2's import-purity assertion is unsatisfiable as design.md words it, because the parent load package imports registry, settings and types
status: open
importance: high
importance_why: Task 4.2's first bullet asserts a property Python cannot provide; the task will block or silently weaken its own guard the moment it starts.
effort: S
kind: inconsistency
area: load-channels, src/fitdocs/load/__init__.py, src/fitdocs/load/channels/__init__.py
created: 2026-08-24
surfaced_by: /kiro-impl load-channels (task 4.1 review round 2, reviewer FOLLOW_UPS; verified independently by the parent session)
pinned_at: 2a1cc3b
resume_command: "/kiro-impl load-channels [queue: .kiro/queue/2026-08-24-channels-package-import-purity-unsatisfiable.md] Rule on how task 4.2 should scope its import-purity assertion before implementing it"
context:
  - .kiro/specs/load-channels/design.md
  - .kiro/specs/load-channels/tasks.md
  - src/fitdocs/load/__init__.py
  - src/fitdocs/load/channels/__init__.py
blocked_by: []
---

## What

`design.md`'s `#### ChannelSurface / PublicSurfacePin` section (design.md:1239-1241)
states:

> Importing `fitdocs.load.channels` must not import `fitdocs.load.engine`,
> `registry`, `profile`, `types`, `settings`, `cli` or `render` — asserted
> directly (1.10, 9.1–9.7).

Task 4.2's first bullet instructs an implementer to assert exactly that. For
three of those seven modules — `registry`, `settings` and `types` — the
property is **structurally unsatisfiable in Python**, and no edit inside the
channel layer can make it true.

Importing any subpackage requires Python to execute its parent package first.
`src/fitdocs/load/__init__.py` imports `registry` (line 18), `settings`
(line 28) and `types` (line 33) at module scope. So `import
fitdocs.load.channels` necessarily runs those imports before a single line of
`channels/__init__.py` executes.

The remaining four (`engine`, `profile`, `cli`, `render`) are genuinely
absent and can be asserted as written.

## Why it matters

Task 4.2 is the task that converts the feature's stated dependency direction
from an assumption into an enforced property — it is the entire point of the
`_Boundary: ChannelSurface — read-only; whole package import graph_` scope. An
implementer starting it has three bad options and one good one, and nothing in
the spec tells them which to take:

- assert it as written → the task is blocked on day one
- silently drop `registry`/`settings`/`types` from the assertion → the guard
  ships looking complete while covering four of seven names, which is this
  repo's recorded "a guard that reds is not a guard that discriminates"
  species one level up
- weaken the assertion to something vacuous that passes
- scope the assertion to the channel **leaf** modules' own import graph, which
  is both satisfiable and the property the design actually cares about

This is a contract two parts of one spec disagree about, which the queue
contract rates `high`. It costs nothing to rule on now and costs a blocked or
falsely-green task later.

## Evidence

Measured this run, on the task 4.1 branch and on `main`, in fresh
interpreters:

```
$ python -c "import sys; import fitdocs.load.channels; \
  print(sorted(m for m in sys.modules \
  if m.startswith('fitdocs.load.') and not m.startswith('fitdocs.load.channels')))"
LEAKED: ['fitdocs.load.registry', 'fitdocs.load.settings', 'fitdocs.load.types']
```

Identical output at `2a1cc3b` (`main`) and on `impl/load-channels` with task
4.1's populated `__init__.py` in place — so the condition is **pre-existing and
not caused by task 4.1**.

Cause, in the parent package:

```
$ grep -n "import" src/fitdocs/load/__init__.py | head
18:from fitdocs.load import registry
28:from fitdocs.load.settings import (
33:from fitdocs.load.types import (
```

The conflicting design sentence is at `.kiro/specs/load-channels/design.md:1239-1241`.

Originally surfaced as `FOLLOW_UPS` item 1 by the task 4.1 round-2 reviewer
subagent; the parent session reproduced it independently before writing this
item, on both branches.

## How to pick it up

1. Read `design.md:1229-1242` (the `ChannelSurface / PublicSurfacePin`
   section) and task 4.2's bullets in `tasks.md`. Note the section marks itself
   `Summary-only.`
2. Reproduce the measurement above on `main`. It takes one command and
   confirms the conflict is real and pre-existing rather than a branch artifact.
3. Read `src/fitdocs/load/__init__.py:15-40` to see why. Confirm the four
   remaining modules (`engine`, `profile`, `cli`, `render`) really are absent
   from the leaked set — they are, so the design sentence is wrong in part,
   not in whole.
4. Take the ruling in Open questions to the maintainer, then either amend
   `design.md` (a spec change, needing the approval its phase requires) or
   record the agreed scoping on task 4.2 before implementing it.

**Done** looks like: task 4.2 can state its assertion in a form that is both
satisfiable and meaningful, with the design document and the task agreeing on
which import graph is under test — the package's or the leaves'.

## Open questions

The ruling this needs, which a picking-up session cannot make alone:

- Is the intended property "importing the channel layer does not pull in the
  load engine's machinery" (satisfiable today, if scoped to the channel leaf
  modules' own imports — no leaf imports any `fitdocs.load.*` sibling, verified
  by the 4.1 reviewer), or the literal package-import statement (not
  satisfiable without restructuring `fitdocs/load/__init__.py`, which
  `training-load` owns and nine specs cite)?
- If the former: does `design.md` get amended, or does task 4.2 carry a
  declared, documented deviation?
- If the latter: is making `fitdocs/load/__init__.py` lazy actually wanted? It
  is a choke-point module and the change would be visible to every spec that
  imports from it — almost certainly out of proportion to the benefit, but it
  is the maintainer's call, not an implementer's.
