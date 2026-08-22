---
id: 2026-07-27-getitem-setdefault-residuals-undocumented
title: __getitem__ and setdefault escape the second-[load]-reader walk and are in neither the closed set nor the documented residuals
status: open
importance: low
importance_why: Narrow tail of a guard whose main perimeter is now closed and documented. Both spellings are unnatural to write by accident, but a future reader auditing the docstring's residual list will not find them named at all.
effort: S
kind: gap
area: training-load, tests/load/test_settings.py
created: 2026-07-27
surfaced_by: /kiro-queue close 2026-07-26-second-load-reader-spellings-escape-guards
pinned_at: 56012ca
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-07-27-getitem-setdefault-residuals-undocumented.md] Name __getitem__ and setdefault in the literal-key walk's residual accounting, or close them"
context:
  - tests/load/test_settings.py
  - .kiro/specs/training-load/tasks.md
  - src/fitdocs/load/settings.py
blocked_by: []
---

## What
`_reads_load_table_literally` (`tests/load/test_settings.py:407-485`) catches
`doc["load"]`, `doc.get("load")` and `dict.get(doc, "load")`. It does not catch
`doc.__getitem__("load")` or `doc.setdefault("load", {})`, and — unlike the
dict-iteration and `.pop` spellings — neither is named anywhere in the guard's
residual accounting.

## Why it matters
The parent item ([[2026-07-26-second-load-reader-spellings-escape-guards]])
closed on the principle that a guard's docstring must describe the perimeter it
actually measured. That holds for the four spellings it enumerated. These two
sit in a third category: not closed, and not listed as accepted either. A
reader auditing the residual list would conclude they are covered.

`__getitem__` is the explicit-dunder twin of the `ast.Subscript` clause that is
already the walk's oldest and most load-bearing check, which makes its absence
the more surprising of the two.

## Evidence
Measured on `main` at `56012ca` by importing the shipped helper and feeding it
ASTs:

```
d["load"]                 -> True
d.get("load")             -> True
dict.get(d, "load")       -> True
d.__getitem__("load")     -> False
d.setdefault("load", {})  -> False
```

`grep -n "__getitem__\|setdefault" tests/load/test_settings.py` returns
nothing — neither spelling appears in any docstring, fixture, or negative
control.

## How to pick it up
Decide per spelling; they are not symmetric.

- `__getitem__` plausibly *can* be closed: unlike `.pop`, an explicit
  `X.__getitem__("load")` has no legitimate instance anywhere in `src/fitdocs`
  (`regions[LOAD_REGION]` is written as a subscript, not a dunder call), so it
  may not carry `.pop`'s false-positive problem. Verify that by adding it to
  the accessor set and running the full suite plus the three existing negative
  controls before believing it.
- `setdefault` mutates and so is a less plausible reader; documenting it as an
  accepted residual may be the honest answer.

Do **not** re-widen the `.pop` / `ast.Compare(==)` clauses while here — `main`
deliberately reverted those after measuring their false positives, and the
negative controls at `tests/load/test_settings.py:662-676` exist to keep them
out. Done when each of the two spellings is either matched by the walk with a
fixture offender, or named in the docstring's residual list with the reason.
