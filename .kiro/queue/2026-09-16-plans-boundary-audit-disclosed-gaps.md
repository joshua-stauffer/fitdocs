---
id: 2026-09-16-plans-boundary-audit-disclosed-gaps
title: Close or widen the disclosed gaps in tests/plans/test_boundary.py's write-target audit and import scans
status: open
importance: medium
importance_why: The audit is the static half of the guarantee that the plan pass never writes under the athlete's plan directory; each gap is a write shape that passes every layer as dead code today, and the runtime guard only sees live code.
effort: M
kind: gap
area: training-blocks, tests/plans/test_boundary.py
created: 2026-09-16
surfaced_by: /kiro-impl training-blocks 4.4 (reviewer, rounds 1-5)
pinned_at: 68fe42e
resume_command: "do: in tests/plans/test_boundary.py close the callable-aliasing gap (flag uncalled write-method attributes with unsafe receivers and uncalled _atomic_write / os.replace names in _scan_expr), then extend the name ban and the engine audit for tempfile.mkstemp(dir=non-derived)/NamedTemporaryFile/os.fdopen/os.open write flags/shutil.*, ban __import__ and importlib across the package, and walk src/fitdocs/render/ wholesale in the reverse-reachability scan; one synthetic control per new rule"
context:
  - tests/plans/test_boundary.py
  - src/fitdocs/plans/engine.py
  - .kiro/specs/training-blocks/design.md
  - tests/test_confinement.py
blocked_by: []
---

## What
The audit's class docstring states its contract as five disclosed gaps. Four
are architectural (path-insensitivity, comprehension/lambda scoping,
interprocedural flow, dynamic dispatch). The fifth, and three scanner
omissions the design's list did not name, are closable:

1. **Callable aliasing**: `_aw = _atomic_write; _aw(source_dir/'leak.md', 'x')`
   and `w = (source_dir/'leak.md').write_text; w('x')` appended to engine.py
   as dead code leave the whole suite green -- `_write_call_target`
   recognises a write only at the `Call` whose `func` is the write attribute.
2. **Write primitives outside the design's list**: `tempfile.mkstemp(dir=<non-derived>)`,
   `tempfile.NamedTemporaryFile`, `os.fdopen`/`os.open` with write flags,
   `shutil.move|copy|copyfile|rmtree` -- a dead helper using
   `mkstemp(dir=source_dir)` + `os.fdopen(fd, 'w')` passes every layer.
3. **Dynamic imports**: `__import__("fitdocs.load")` /
   `importlib.import_module(...)` are invisible to the import-closure and
   forbidden-target layers (import statements only).
4. **Reverse reachability** walks `render/views.py` only (as designed);
   `render/frontmatter.py` and the rest of `render/` are outside it.

## Why it matters
`tests/test_confinement.py`'s `plan` entry point catches a real write under
the source directory only when the staged fixture's run executes it. Dead or
conditional code is the static audit's job, and these four shapes are exactly
the ones it does not see.

## Evidence
- `tests/plans/test_boundary.py:1015-1022` -- the contract paragraph naming
  callable aliasing as the queued fifth gap.
- 4.4 reviewer mutations V13/V14 (round 5: whole suite green with the alias
  helper in engine.py), O26/N14 (mkstemp+fdopen, rounds 1-2), O4b
  (`__import__`, round 1), O24e (`render/frontmatter.py`, round 1) -- all
  reported by the reviewer subagent with the suite counts; reproduce by
  appending the helper to `src/fitdocs/plans/engine.py` and running
  `uv run pytest tests/plans/test_boundary.py tests/test_confinement.py -q`.

## How to pick it up
1. Read `_EngineWriteTargetAudit`'s class docstring (the contract), then
   `_scan_expr`, `_write_call_target`, `_write_name_offenders_in_tree`,
   `TestForbiddenNames`, `TestReverseReachability`.
2. For each gap: add the rule, a synthetic positive control asserting exactly
   one offender at the write line, and confirm
   `_EngineWriteTargetAudit(<real engine tree>).offenders() == []` still holds.
3. Update the contract paragraph (five -> four disclosed gaps, or fewer).
   Done when every mutation above reds and the full suite is green.
