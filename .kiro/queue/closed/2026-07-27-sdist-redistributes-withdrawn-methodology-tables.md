---
id: 2026-07-27-sdist-redistributes-withdrawn-methodology-tables
title: The sdist redistributes both extracted tables; no guard inspects it
status: done
importance: high
importance_why: Req 13.1 says the built distribution ships no withdrawn-methodology data files, and the wheel honours it — but `uv build --sdist` includes the extracted tables and the writeup verbatim. The workbook carried the third party's copyright notice and redistribution permission was never obtained. Publishing an sdist to PyPI would distribute them.
effort: M
kind: bug
area: training-load, tests/load/test_packaging.py, pyproject.toml
created: 2026-07-27
surfaced_by: adversarial review of chore/withdrawal-guards-widen (queue sweep 2026-07-27)
pinned_at: 80cc5c5
resume_command: "do: stop the sdist from redistributing the extracted tables and the writeup — decide between an sdist exclude in pyproject.toml and moving the research record outside the packaged tree, then extend the withdrawal guards in tests/load/test_packaging.py to inspect the SDIST as well as the wheel, with an explicit exemption for whatever the retained research record ends up being [queue: .kiro/queue/closed/2026-07-27-sdist-redistributes-withdrawn-methodology-tables.md]"
context:
  - tests/load/test_packaging.py
  - pyproject.toml
  - .kiro/specs/training-load/requirements.md
blocked_by: []
---

## What

Every withdrawal guard in `tests/load/test_packaging.py` inspects the built
**wheel**. The sdist is never inspected, and it is materially different:
`uv build --sdist` produces 403 members including
both extracted-table files, the writeup,
and even `.kiro/queue/`. The wheel, by contrast, contains 63 members and zero
under `docs/`.

So training-load Req 13.1 — "the built distribution shall ship no withdrawn-methodology
data files" — is satisfied for one of the two artifacts `uv build` produces, and the
guards' docstring claim to prove absence "in a distribution" is true only of
the wheel.

## Why it matters

This is a licensing exposure, not defence-in-depth. The workbook carried
the third party's copyright notice, and the tables were extracted under
an explicitly unresolved permission question (see the callout in
the writeup). The methodology was later *withdrawn*
rather than licensed (training-load Amendment 2, 2026-07-25). Publishing an
sdist to PyPI would redistribute both extracted tables verbatim.

Note the fix is not a one-line prefix change: naively extending the widened
wheel guard to the sdist would red on the extracted tables, which
training-load task 5.2 and `design.md:1739` both **require** stay in place.
The retained research record needs an explicit exemption, or needs to move
outside the packaged tree.

## Evidence

```
$ uv build --sdist   # 403 members, including:
both extracted-table files
the writeup
.kiro/queue/

$ # wheel, for contrast: 63 members, zero under docs/
```

Gathered by the adversarial reviewer of `chore/withdrawal-guards-widen`
(2026-07-27), which widened the wheel guards to catch renamed data files and
renamed modules but left the sdist uninspected. Guard sites:
`tests/load/test_packaging.py:259-273` (wheel member walk),
`tests/load/test_packaging.py:189` (the original `.csv` check).

`src/fitdocs/data/` is safe only by accident — `.gitignore`'s `data/` entry
makes hatchling drop it; that is not a deliberate control.

## How to pick it up

1. Read `.kiro/specs/training-load/requirements.md` Req 13.1 and decide whether
   "built distribution" was always meant to cover the sdist. It almost
   certainly was — say so explicitly rather than silently widening.
2. Run `uv build --sdist` and list the members yourself before changing
   anything, so the fix is measured against the real artifact.
3. Choose: an sdist exclude in `pyproject.toml`, or relocating the research
   record outside the packaged tree. The second is cleaner but must not break
   training-load task 5.2 / `design.md:1739`, which require the writeup and
   its extracted tables stay in place.
4. Extend the guards to inspect the sdist, with fixture discrimination: land a
   `.csv` under the packaged tree, show the sdist guard RED, remove it, GREEN.

Done looks like: no withdrawn-methodology-derived data file in either artifact, a guard that
proves it for both, and the retained research record still exactly where task
5.2 requires.

## Resolution

Closed 2026-07-29, merged to `main` as `fb1eba1` + `0080811`
(branch: the sdist exclusion for the withdrawn methodology's tables, `--ff-only`, validated after rebase:
2090 passed, ruff check + `ruff format --check` + mypy clean).

**Route taken**: the sdist-exclude, not relocation. `pyproject.toml` gains a
`[tool.hatch.build.targets.sdist]` stanza excluding
the writeup and the extracted tables. Relocation
was independently ruled out by the reviewer: the deleted writeup-sourced-constant
test reads the writeup
from the source tree and asserts `_WITHDRAWN_TABLE_VALUES` stay sourced verbatim
from it, so moving the file would red an existing guard. training-load
`tasks.md` task 5.2 and `design.md:1751-1753` independently require the files
stay in the checkout.

**Artifact evidence** (reviewer built it, rather than trusting the test):
`uv build --sdist` → 469 members; the writeup and both extracted-table files
absent; 60 `src/fitdocs/` members
present. The extracted sdist still builds a working wheel identical to a
direct wheel build. The wheel guard is byte-identical to `main` — the whole
diff has zero deletions.

**Discrimination**: partial-exclude mutations confirm each path branch is
independently load-bearing (un-excluding only the writeup reds naming exactly
it; un-excluding only the extracted tables' directory reds naming exactly the two CSVs), so a guard
checking only one of the three files is ruled out. The vacuous-walk positive
control was proved to fire by excluding `src/` from the sdist — build still
succeeds, archive non-empty, and the guard reds with "this guard's archive is
empty or malformed".

**Known residual, deliberately not fixed here** (queued separately): the guard
was path-literal, so renaming the extracted tables' directory
shipped both CSVs with the suite green. The durable fix is content-keyed.

**Superseded 2026-08-01**: `encumbered-content-purge` task 3.1 deleted the
writeup, both extracted tables and the sdist-exclude stanza this resolution
describes from the working tree entirely, per Requirement 4's reversal of
their retention.
