---
id: 2026-07-26-load-table-read-bypasses-settings-reader
title: A module could read the `[load]` table by bypassing `load_load_settings` entirely via a direct `tomllib.load`
status: open
importance: medium
importance_why: Req 14.1 promises "no second reader of that table shall exist anywhere in the tool"; every guard in tests/load/test_settings.py enforces that against calls that go *through* fitdocs.settings.load_settings_document or the load_load_settings function object, but nothing stops a module from opening the settings file directly with tomllib.load and reading `[load]` off the parsed document itself, never touching either.
effort: M
kind: gap
area: training-load, athlete-benchmarks, tests/load/test_settings.py, src/fitdocs/settings.py
created: 2026-07-26
surfaced_by: kiro-impl remediation round 1, queue/2026-07-26-second-load-reader-spellings-escape-guards
pinned_at: c3d2201
resume_command: "/kiro-spec-requirements training-load [queue: .kiro/queue/2026-07-26-load-table-read-bypasses-settings-reader.md] Close the tomllib.load bypass of the [load]-table reader guards"
context:
  - tests/load/test_settings.py
  - src/fitdocs/settings.py
  - src/fitdocs/quarantine.py
  - src/fitdocs/athlete.py
  - src/fitdocs/load/profile.py
blocked_by: []
---

## What
`tests/load/test_settings.py` carries several guards (an AST call-site walk,
an AST literal-key walk, and a behavioral `sys.modules` sweep) that together
close every escape found so far for a second reader of the `[load]` settings
table -- *provided* the offending code eventually calls
`fitdocs.load.settings.load_load_settings` or reads a dict that
`fitdocs.settings.load_settings_document` produced. None of them can see a
module that instead calls `tomllib.load` directly against the settings file
path and reads `"load"` off the result itself: that module never calls
`load_load_settings` (so the call-site walk and the behavioral sweep are
blind to it) and, depending on how it reads the key, may or may not trip the
literal-key walk -- and even if it does, the literal-key walk only catches
the specific `Subscript`/`.get` shapes it already enumerates.

## Why it matters
This is a real gap in a Req 14.1 guarantee, not a hypothetical: three
modules already call `tomllib.load` legitimately for other files
(`quarantine.py:156`, `athlete.py:114`, `load/profile.py:299`), so a guard
cannot be as simple as "no module besides `fitdocs/settings.py` calls
`tomllib.load`" -- it would need to distinguish a `tomllib.load` call
against the settings-file path specifically. This is also the reason
spellings (1)-(3) named in the sibling behavioral-companion docstring (the
aliased-key read, the unbound-method form, and the un-enumerated mapping
accessor) are accepted as residual rather than closed by a
construction-closing fix: instrumenting `load_settings_document` itself and
attributing reads by caller frame would still not be airtight while this
direct-`tomllib.load` path remains open, so that fix was judged not worth
attempting until this gap is addressed (or accepted more formally).

## Evidence
- `src/fitdocs/quarantine.py:156` -- legitimate `tomllib.load` call, not
  against the settings file.
- `src/fitdocs/athlete.py:114` -- legitimate `tomllib.load` call, not against
  the settings file.
- `src/fitdocs/load/profile.py:299` -- legitimate `tomllib.load` call, not
  against the settings file.
- `grep -rn "tomllib.load" src/fitdocs` confirms these are the only current
  callers; no guard in the suite pins `fitdocs/settings.py` as the sole
  caller of `tomllib.load` against the settings path.
- `tests/load/test_settings.py` (lines documenting the escape, ~350-372 as of
  `pinned_at`) records this reasoning inline but does not attempt a fix.

## How to pick it up
1. Read `tests/load/test_settings.py`'s call-site and literal-key walk
   docstrings in full for the exact enumerated escapes already known.
2. Decide the guard shape: likely an AST check for `ast.Call` to
   `tomllib.load` (or `tomllib.loads`) whose argument resolves to the
   settings-file path (or, more conservatively, flag *any* `tomllib.load`
   call outside `fitdocs/settings.py` and allowlist the three known
   legitimate callers by file, then require new callers to justify
   themselves the same way).
3. Measure the guard the same way this session measured its siblings: add a
   real second reader using `tomllib.load` directly (e.g. to
   `src/fitdocs/audit.py`), confirm the full suite is otherwise green before
   the new guard exists, then confirm the new guard reddens on exactly that
   file.
4. If a guard is judged unbounded/not worth adding, replace the
   "recorded as a design-signal follow-up" line in `test_settings.py` with a
   citation of this item's `status: dropped` and the reasoning, rather than
   leaving it open-ended.

## Open questions
Whether an allowlist-of-legitimate-callers guard (brittle, needs updating
whenever a new legitimate `tomllib.load` caller is added) is worth the
maintenance cost versus formally accepting this as permanent residual and
saying so plainly in the design docs for Req 14.1.
