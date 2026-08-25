---
id: 2026-08-24-channels-package-import-purity-unsatisfiable
title: design.md's ChannelSurface import-purity sentence is unsatisfiable as worded; task 4.2 has a ruling, the design still needs amending
status: open
importance: medium
importance_why: Ruled for task 4.2 on 2026-08-25 so the task is unblocked; design.md still states a property Python cannot provide, which will mislead the next reader of the spec.
effort: S
kind: inconsistency
area: load-channels, src/fitdocs/load/__init__.py, src/fitdocs/load/channels/__init__.py
created: 2026-08-24
surfaced_by: /kiro-impl load-channels (task 4.1 review round 2, reviewer FOLLOW_UPS; verified independently by the parent session)
pinned_at: 2a1cc3b
resume_command: "do: amend .kiro/specs/load-channels/design.md:1239-1241 so its import-purity sentence matches the 2026-08-25 ruling recorded on task 4.2 in tasks.md -- package-level for engine/profile/cli/render, leaf-level for all seven -- following whatever re-approval the spec phase requires"
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
4. Read the **Ruling** section below and the declared deviation on task 4.2 in
   `tasks.md` (commit `bf10391`). The implementation question is settled; what
   is left is amending `design.md` to match, as a spec change.

**Done** looks like: `design.md:1239-1241` no longer states a property Python
cannot provide, and it agrees with the guard task 4.2 actually shipped.

## Ruling (2026-08-25)

The maintainer ruled on the task-4.2 half: **scope the assertion to the channel
leaf modules**, and assert both halves —

- (a) at package-import level, the four genuinely-absent names: `engine`,
  `profile`, `cli`, `render`
- (b) at leaf level, that no module inside `channels/` imports any
  `fitdocs.load.*` sibling — which covers all seven names and is the
  dependency-direction property the design is actually protecting

Explicitly **not** chosen: silently dropping the three names from a
package-level assertion (ships a guard reading as complete while covering four
of seven), and making `fitdocs/load/__init__.py` lazy (a choke point nine specs
cite and `training-load` owns — blast radius out of proportion to the benefit).

The ruling is recorded as a declared deviation on task 4.2 in
`.kiro/specs/load-channels/tasks.md` (commit `bf10391`), so the implementing
session reads it in place.

**What remains for this item:** `design.md:1239-1241` still asserts the
unsatisfiable property. Amending it is a spec change needing its phase's
re-approval, which is why it was not folded into the implementation branch.

## Open questions

None on the task-4.2 half — ruled 2026-08-25, see Ruling above.

Remaining for the design amendment: whether `design.md:1239-1241` should be
rewritten to state the two-level property the ruling adopted, or simply be
scoped to the four package-level names with the leaf-level property stated
separately. Either matches the shipped guard; it is an editorial choice about
how the design reads, and it needs whatever re-approval the spec's phase
requires.
