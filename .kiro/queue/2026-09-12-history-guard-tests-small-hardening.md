---
id: 2026-09-12-history-guard-tests-small-hardening
title: Seven small hardening gaps in the load-history guard and unit tests (exemption keying shape, identity pins on interned values, consumer-guard positive control, _quote escaping, math.isfinite on huge ints, "1 pages", forbidden-scan synthetic control)
status: open
importance: low
importance_why: Each is a guard that could report green on a defect it was written to catch, or a cosmetic slip; none is reachable by shipped data today.
effort: M
kind: gap
area: load-history, tests/history/test_constant_guard.py, tests/test_public_api.py, tests/test_contract_consumers.py, src/fitdocs/history/page.py, src/fitdocs/history/series.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history (reviewer FOLLOW_UPS across 2.1, 3.1, 4.2, 5.4, 5.6)
pinned_at: 8cd0062
resume_command: "do: work the seven items below one commit each; each done when its named negative control fails before the fix and passes after"
context:
  - tests/history/test_constant_guard.py
  - tests/test_public_api.py
  - tests/test_contract_consumers.py
  - tests/history/test_boundary.py
  - src/fitdocs/history/page.py
  - src/fitdocs/history/series.py
blocked_by: []
---

## What
1. **Exemption table keying** (`test_constant_guard.py`): entries keyed
   `(None, None, value)` match any site; the count-matched `Counter` shape
   means a literal moved from one function to another still matches. Key by
   `(module, qualname, value)` and require exact multiplicity per site.
2. **Identity pins vacuous for interned values** (`test_public_api.py`,
   `test_contract_consumers.py`): `is` on small ints / short strings passes
   even when the module re-declares the constant. Pin by identity only for
   objects (functions, classes, enums); pin value+source for scalars.
3. **Consumer-guard AST walk lacks a positive control**: nothing proves the
   walk finds a from-import in a fixture module. Add one.
4. **`page._quote` escaping unpinned**: a methodology id containing `"` or
   `\` round-trips only by luck. Pin `a"b`, `a\b`, `a: b`.
5. **`math.isfinite` raises OverflowError** on a huge int load
   (`isfinite(10**400)`) in `series.py`'s load validation; the intended
   outcome is a skipped page, not a crash. Convert via `float()` in a
   try/except first.
6. **"1 pages"** grammar in `page._plural` for one path (the coverage
   intro's "of N documents read" bypasses `_plural`).
7. **`_forbidden_scan_targets_for_path` has no synthetic control**
   (`test_boundary.py`): the helper that maps a history module to the
   modules it must not import is exercised only on the real tree, so a
   helper that returns an empty set for every path passes. Feed it a
   synthetic package and assert the expected set.

## Evidence
Reviewer `FOLLOW_UPS`: 2.1 R3 (1), 5.4 R3 (2, 3), 4.2 R2 (4, 6), 3.1 R3 (5).

## How to pick it up
Independent; any order. Each has its negative control named above.
