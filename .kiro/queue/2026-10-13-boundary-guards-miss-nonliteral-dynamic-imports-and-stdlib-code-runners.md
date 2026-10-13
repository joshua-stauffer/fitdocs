---
id: 2026-10-13-boundary-guards-miss-nonliteral-dynamic-imports-and-stdlib-code-runners
title: The query, compose and dashboards boundary guards cannot see a non-literal dynamic import, and a dynamic-import ban that lists bad stdlib modules cannot close the stdlib modules that run source text
status: open
importance: medium
importance_why: The guards exist to stop a forbidden dependency (duckdb in dashboards, fitdocs.cli in query, a clock anywhere); a computed module name or a stdlib code runner reaches the same surface with the suite green.
effort: M
kind: gap
area: dashboards, analytics-query, tests/query/test_boundary.py, tests/dashboards/test_boundary.py, tests/compose/test_boundary.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 8.4 reviewer, two findings combined)
pinned_at: 0a98d5c
resume_command: "do: make tests/query/test_boundary.py _import_targets report a dynamic import whose module name is not a string literal (record a sentinel target the guards refuse), switch the dashboards external rule from naming bad stdlib modules to allowlisting the stdlib roots each module uses, and give tests/compose/test_boundary.py the same dynamic-import treatment; add a synthetic control for each [queue: .kiro/queue/2026-10-13-boundary-guards-miss-nonliteral-dynamic-imports-and-stdlib-code-runners.md]"
context:
  - tests/query/test_boundary.py
  - tests/dashboards/test_boundary.py
  - tests/compose/test_boundary.py
  - .kiro/specs/dashboards/design.md
  - .kiro/queue/2026-09-12-import-guards-scope-gaps.md
  - .kiro/queue/2026-09-17-plans-boundary-package-root-import-smuggling.md
blocked_by:
  - dashboards
---

## What
Two weaknesses of one family, both in the AST guards that police what a
package may import.

1. **Non-literal dynamic imports are invisible to the shared parser.**
   `_import_targets` in `tests/query/test_boundary.py:24` resolves
   `importlib.import_module(...)` and `__import__(...)` only when the first
   argument is a string literal (`isinstance(module_name, ast.Constant)`, line
   126). A computed name produces no target. The dashboards guard imports this
   parser (`tests/dashboards/test_boundary.py:54`) and the query guards are
   built on it. Compose has its own `_import_targets`
   (`tests/compose/test_boundary.py:173`) that handles static `import` and
   `from` only, with no dynamic-import handling at all.
2. **The stdlib is allowed wholesale.** The dashboards external rule skips every
   stdlib target (`if _is_stdlib(target): continue`, `_external_violations` in
   `tests/dashboards/test_boundary.py:264`), and the dynamic-import
   ban lists the modules it knows are bad (`_DYNAMIC_ROOTS` = importlib,
   builtins, pkgutil, runpy, zipimport, plus the builtins `exec`, `eval`,
   `compile`; lines 169-178). Any stdlib module that runs or locates code and is
   not in the list passes: `code`, `codeop`, `timeit`, `pydoc.locate`. The
   enumeration can never be complete.

## Why it matters
The dashboards package must never import `duckdb`, `fitdocs.index` or a clock
(design § Allowed Dependencies); query must not import `fitdocs.cli`. Both are
the kind of rule a one-line `importlib.import_module(name)` defeats. The suite
is green over that route today, so the guards give more assurance than they
provide.

## Evidence
Run at 0a98d5c with `PYTHONPATH=.:src` against the real guard functions:

```
query guard _query_import_violations({"fitdocs.query.command": ...})
  literal   importlib.import_module('fitdocs.cli')                 -> [('fitdocs.query.command', 'fitdocs.cli')]
  non-literal  name = 'fitdocs.' + 'cli'; importlib.import_module(name) -> []
  non-literal  name = 'duck' + 'db'; __import__(name)                    -> []

shared parser _import_targets(src, 'fitdocs.dashboards.engine')
  import_module('duckdb')                          -> ['duckdb', 'importlib']
  name = 'duck' + 'db'; import_module(name)        -> ['importlib']
  name = 'duck' + 'db'; __import__(name)           -> []

dashboards _external_violations / _dynamic_import_violations on the engine module
  import ftplib | smtplib | xmlrpc.client | imaplib | asyncio | subprocess -> external=[] dynamic=[]
  import code | codeop | timeit                                              -> external=[] dynamic=[]
  import pydoc; pydoc.locate('os')                                           -> external=[] dynamic=[]
  import importlib                                                           -> dynamic=['importlib']
```

(`import socket` is caught: `external=['socket']`.) In the dashboards package
the literal `importlib` import is itself banned, so the non-literal route is
closed there by the dynamic ban; the open routes are the stdlib code runners
above, and the query and compose packages, which have no such ban.

Reported by the 8.4 reviewer subagent as two findings ("`_import_targets` skips
non-literal dynamic imports; every boundary guard built on it has the blind
spot" and "the dynamic-import rule enumerates bad stdlib modules rather than
allowlisting used stdlib roots"); both reproduced here.

## How to pick it up
1. Read `_import_targets` in `tests/query/test_boundary.py` (lines 24-200) and `TestNoDynamicImports` in `tests/dashboards/test_boundary.py` (line 910 onward).
2. Fix 1: when `dynamic` is true and the module-name argument is not a string literal, record a sentinel target (for example `<dynamic>`) that every consumer treats as a violation, and add a synthetic control per route (computed name for `import_module` and for `__import__`). Mirror it in `tests/compose/test_boundary.py` or have compose import the shared parser.
3. Fix 2: replace the "known bad stdlib module" enumeration with an allowlist of the stdlib roots each dashboards module actually imports (derive it from a measured scan, as the existing external allowlists do), so a new stdlib import has to be added on purpose.
4. Done means each probe above reds against its guard, and the live scan is still green.

## Open questions
Whether allowlisting stdlib roots per module is worth the upkeep for query and compose as well, or only for dashboards (the package with the strictest rule). Related, narrower items: `2026-09-12-import-guards-scope-gaps` (other packages' guards) and `2026-09-17-plans-boundary-package-root-import-smuggling` (the plans copy of `_import_targets`).
