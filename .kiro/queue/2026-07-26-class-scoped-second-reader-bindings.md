---
id: 2026-07-26-class-scoped-second-reader-bindings
title: The __defaults__/__kwdefaults__ reader spy only walks vars(module); a class-scoped binding still escapes it
status: open
importance: medium
importance_why: Two real, reachable second-reader spellings on the `fitdocs check` path leave the package-wide spy's `checked` assertion (`calls == 0`) passing, the same shape of gap Req 14.1 exists to close.
effort: S
kind: gap
area: training-load, tests/load/test_settings.py
created: 2026-07-26
surfaced_by: /kiro-impl training-load (round 3 review of queue/2026-07-26-second-load-reader-spellings-escape-guards)
pinned_at: c3d2201
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-07-26-class-scoped-second-reader-bindings.md] Decide whether to descend into class objects in the reader-spy sweep or formally accept class-scoped bindings as an open residual"
context:
  - tests/load/test_settings.py
  - src/fitdocs/load/settings.py
  - src/fitdocs/audit.py
blocked_by: []
---

## What
`test_load_load_settings_is_called_the_documented_number_of_times_per_command` (`tests/load/test_settings.py`) rewrites, in place, any function's `__defaults__`/`__kwdefaults__` slot that still holds the pre-patch `load_load_settings`, but only for function objects it finds directly in `vars(module)` for each already-imported `fitdocs.*` module. Four spellings still escape it, measured as real calls reached from inside `audit()` on the `fitdocs check` path. The first two hide one level deeper than the sweep walks; the second two never appear in `vars(module)` at all:

1. **A class-body binding** -- `class _Holder: reader = load_load_settings` then `_Holder.reader(document, path)`. The binding lives in `vars(_Holder)`, not `vars(module)`; the sweep never descends into a class object it finds in a module's namespace.
2. **A class-held `__defaults__`** -- a `@staticmethod` on a class body whose keyword default is the reader. The function itself is never enumerated, because it lives in `vars(cls)`, one level below what the sweep walks.
3. **A PEP 562 module `__getattr__` attribute** -- a module that returns the
   reader from a private container via a module-level `__getattr__` hook.
   `module._hidden_reader is load_load_settings` is true, but `_hidden_reader`
   is never a key in `vars(module)`, so the sweep never sees it to rebind it.
   This is the sharpest of the four: `src/fitdocs/__init__.py` already uses
   PEP 562 module `__getattr__` for its lazy re-exports and says so in its own
   docstring, so it is an established pattern in this package, not a contrivance.
4. **A `functools.partial(load_load_settings)`** bound as a module attribute.
   The attribute's value is a `partial`, not the reader, so the sweep's
   `is original` identity test does not match it; the reader survives inside
   `partial.func`.

## Why it matters
Both are real invocations of `load_load_settings` on a path the test documents as calling it zero times, and both leave that assertion passing. The docstring above the test and the comment block above it (`tests/load/test_settings.py`, the `--- Package-wide behavioral companion ---` section) now name both as measured, open residuals rather than claiming the sweep's coverage of def-time bindings is complete -- this item is where the decision about whether to close them belongs, not another docstring round.

## Evidence
Measured 2026-07-26: adding both bindings to `src/fitdocs/audit.py` (a class holding `reader = load_load_settings` as a class attribute, and a `@staticmethod` with the reader as a keyword default, both invoked from inside `audit()` against real frontmatter) left the full suite at 1991 passed, `ruff check .` clean, and `uv run mypy` clean -- including `tests/load/test_settings.py`'s own 25 tests, all green. Reverted; suite still 1991 passed, ruff and mypy clean.

Spellings 3 and 4 measured independently on 2026-07-26 by the round-3 reviewer
of the parent item, by the same method: each invokes the reader once from
inside `audit()` where the assertion documents zero, and each leaves the full
suite at 1991 passed with `ruff check .` and `uv run mypy` clean.

## How to pick it up
Read the `--- Package-wide behavioral companion ---` comment block and `test_load_load_settings_is_called_the_documented_number_of_times_per_command` in `tests/load/test_settings.py` for the exact sweep code and its stated (not claimed-complete) perimeter. Decide first whether to extend the sweep (walking `type` objects found in `vars(module)` and their own `vars(cls)` closes spellings 1 and 2 and invites the next nesting level; spellings 3 and 4 are not a nesting problem at all and would need different mechanisms again -- resolving `module.__getattr__` for a candidate name set, and unwrapping `functools.partial.func`), or to formally accept class-scoped bindings as out of this guard's scope alongside the AST walk's aliased-key residual. Whichever is chosen, state it as what was measured, not as a claim that the resulting perimeter is complete.
