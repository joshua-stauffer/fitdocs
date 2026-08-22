---
id: 2026-07-27-withdrawal-evasions-one-level-up
title: The withdrawal guards watch `fitdocs/load/`, so the same evasions work one directory up
status: open
importance: low
importance_why: Nothing is trying to reintroduce the methodology; this is defence-in-depth on a settled withdrawal. But the directory-keyed guard reproduces the exact rename hole it was written to close, one level higher, and the two largest withdrawn tables have no constant guard at all.
effort: M
kind: gap
area: training-load, tests/load/test_packaging.py
created: 2026-07-27
surfaced_by: adversarial review of chore/withdrawal-guards-widen (queue sweep 2026-07-27)
pinned_at: 80cc5c5
resume_command: "do: decide whether the withdrawal guards should watch the whole package rather than `fitdocs/load/`, and whether the zone-pace and race-equivalent tables need constant coverage — the reviewer's suggested shape-keyed alternative (an AST scan for any class matching the LoadCalculator member set) fires once instead of 21 times as sibling specs land [queue: .kiro/queue/2026-07-27-withdrawal-evasions-one-level-up.md]"
context:
  - tests/load/test_packaging.py
  - .kiro/specs/training-load/requirements.md
blocked_by: []
---

## What

`chore/withdrawal-guards-widen` replaced a name-keyed denylist with a
directory-level allowlist over `fitdocs/load/`. That closes renames *inside*
that directory and reproduces the same hole immediately outside it. Three
evasions were executed and left the suite green:

1. **Renamed calculator one level up.** `src/fitdocs/scoring.py` containing
   a class built from the methodology's trademarked abbreviation, with a
   `compute` method, ships in the wheel: 1869 passed. `_WITHDRAWN_SYMBOLS`
   matches only `WithdrawnCalculator` / `fitdocs.load.withdrawn`. The
   allowlist is prefixed to `fitdocs/load/`.
2. **Bundled table one level up.** The real withdrawn table copied verbatim to
   `src/fitdocs/tables/paces_by_zones.csv` appears in the wheel member list:
   1869 passed. The identical file under `fitdocs/load/` reds.
3. **Methodology as a Python literal inside an allowlisted module.** Real rows
   from the withdrawn methodology's pace table and its race-equivalent table,
   copied verbatim from the extracted tables, appended to
   `src/fitdocs/load/types.py`: 1869 passed. The
   `_WITHDRAWN_TABLE_VALUES` guard covers five zone-6/7 discount factors only.
   The two largest tables in the withdrawn methodology have no coverage at
   all.

## Why it matters

Low urgency: nothing is trying to reintroduce the withdrawn methodology, and the withdrawal is
settled. What makes it worth recording is that the guard's *shape* is the
problem, not its contents — keying to a directory has the same class of hole as
keying to a name, just one level up, and the guards' own docstring reasons
about `fitdocs/load/` as if it were the whole surface.

The reviewer also proposed a formulation that does not go stale: an AST scan
flagging any module under the package that defines a class with the
`LoadCalculator` protocol's member set (`name` / `supports` /
`required_athlete_fields` / `compute`). That stays silent through all seven
`load-channels` modules and all nine `activity-qa-flags` modules — none is a
calculator — and fires exactly once, on `threshold-load`'s
`load/threshold/calculator.py`, which is precisely when Req 13.1/13.2's "ships
no methodology" invariant genuinely needs re-deciding. One trip instead of 21.

## Evidence

All three evasions executed by the adversarial reviewer of
`chore/withdrawal-guards-widen` (2026-07-27), each through `uv run pytest`,
each leaving `1869 passed`. Guard sites: `tests/load/test_packaging.py:57`
(`_WITHDRAWN_SYMBOLS`), `:69-75` (`_WITHDRAWN_TABLE_VALUES`), `:259-273` (the
directory-scoped wheel walk).

Note `src/fitdocs/data/` is safe only by accident: `.gitignore`'s `data/` entry
makes hatchling drop it. The reviewer had to work around that to demonstrate
evasion 2.

## How to pick it up

1. Read `tests/load/test_packaging.py` in full and
   `.kiro/specs/training-load/requirements.md` Req 13.1/13.2 — the question is
   what surface the requirement was always about, not what the guard happens to
   check.
2. Reproduce evasion 1 yourself before changing anything.
   **Superseded 2026-08-01**: evasion 3 can no longer be reproduced.
   `encumbered-content-purge` task 3.1 deleted its source tables from the
   working tree.
3. Weigh the shape-keyed AST scan against simply re-prefixing the existing
   checks to the whole package. The AST scan is more work but does not need
   editing as the ~21 specified sibling modules land.
4. Whatever lands needs fixture discrimination per change-protocol.md, and must
   not fire on the extracted tables, which training-load task 5.2
   requires stay in place. **Superseded 2026-08-01**: `encumbered-content-purge`
   task 3.1 deleted the extracted tables and the writeup from the working tree
   entirely, per Requirement 4's reversal of their retention. This constraint
   no longer has a subject in the tree.

Related: `.kiro/queue/closed/2026-07-27-sdist-redistributes-withdrawn-methodology-tables.md`
covers the sdist, which is the higher-priority half of the same guard gap.
