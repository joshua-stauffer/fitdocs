---
id: 2026-07-28-shapes-guard-tuple-targets-bypass
title: Tuple and starred assign targets bypass the shapes-only guard's permitted-name check
status: open
importance: low
importance_why: A supplementary strictness check in `tests/test_citation.py` passes vacuously for tuple targets, because the `ast.Name` comprehension yields an empty set and `set() <= permitted` is trivially true. No Requirement 15/16 violation can slip through — the whole-module walk still catches records and arithmetic in tuple targets — so this is defence-in-depth with a hole, not a live gap.
effort: S
kind: gap
area: fit-ingest, tests/test_citation.py
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 8.1 review, round 4 — reviewer's own mutations)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-28-shapes-guard-tuple-targets-bypass.md] Close the tuple/starred-target bypass in the shapes-only AST guard"
context:
  - tests/test_citation.py
  - src/fitdocs/citation.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`test_module_holds_no_arithmetic_and_no_records` in `tests/test_citation.py`
carries a supplementary rule that every module-scope assignment target must be
one of two permitted names (`SourceRecord`, `_N`). It extracts target names
with a comprehension over `ast.Name` targets. For a tuple target
(`_A, _B = 1, 2`) the targets list holds a single `ast.Tuple`, not `ast.Name`,
so the comprehension yields the empty set and the containment check
`set() <= permitted_assign_targets` passes vacuously. The `else` branch that
looks like it handles the non-`Name` case is unreachable for `ast.Assign`.

## Why it matters

Low. The guard's primary assertions — no `ast.Call` to a record type and no
arithmetic `ast.BinOp` anywhere in the module — walk the entire tree and are
unaffected, so the shapes-only contract that Requirements 15.x/16.x depend on
is intact. The reviewer verified this directly: `_A, _B = Departure(...), 1`
and `_A, _B = 100.0 / 3600.0, 1` both still red.

What is lost is the extra strictness that the module holds *only* the two
permitted module-scope bindings. That rule exists so an unexpected name cannot
accumulate in a file whose whole point is to contain shapes and nothing else,
and it is stated in the guard's docstring as though it holds unconditionally.

## Evidence

At `8e3cb05`, appending either of these to `src/fitdocs/citation.py` leaves
`uv run pytest` at 2108 passed:

```python
_A, _B = 1, 2
```
```python
*_C, _D = [1, 2, 3]
```

Whereas the payload-carrying variants are still caught, confirming the primary
assertions are sound and only the name rule is bypassed:

```python
_A, _B = Departure(subject="s", source_specifies="x", fitdocs_does="y", reason="r"), 1   # RED
_A, _B = 100.0 / 3600.0, 1                                                               # RED
```

The single-name form is correctly caught: `_SCALE = 100.0 / 2.0 + 1` reds, and
`BAD_NAME = 5` inside a module-level `if True:` reds.

## How to pick it up

1. Read `test_module_holds_no_arithmetic_and_no_records` in
   `tests/test_citation.py` — specifically the target-name extraction and the
   `module_scope_statements` helper it walks.
2. Replace the `ast.Name`-only comprehension with one that flattens tuple and
   starred targets: walk each target with `ast.walk` and collect every
   `ast.Name.id`, or handle `ast.Tuple`/`ast.List`/`ast.Starred` explicitly.
   Keep the existing `ast.AnnAssign` handling.
3. Done looks like: `_A, _B = 1, 2` and `*_C, _D = [1, 2, 3]` each red this test
   alone, `_SCALE = 100.0 / 2.0 + 1` and `BAD_NAME = 5` still red, and the
   module's own legitimate `SourceRecord = ...` and `_N = TypeVar(...)`
   assignments keep the suite green.
4. While there, note the reviewer's paired observation recorded at
   `2026-07-28-shapes-guard-vars-justification-inverted` — same file, same
   test module, worth doing in one sitting.

## Open questions

None. The fix is mechanical and the mutations that prove it are named above.
