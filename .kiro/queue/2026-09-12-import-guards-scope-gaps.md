---
id: 2026-09-12-import-guards-scope-gaps
title: Import/purity guards are scoped to import statements and miss dynamic/attribute/literal routes
status: open
importance: medium
importance_why: Several purity and single-writer guards only scan import statements, so importlib/attribute-chain/string-literal routes into the same forbidden surface pass undetected today.
effort: M
kind: gap
area: performance-benchmarks, tests/performance/test_single_writer.py, test_reachability.py, tests/test_contract_consumers.py, tests/load/channels/test_purity.py, tests/load/threshold/test_boundary.py
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "do: harden test_single_writer.py, test_reachability.py, test_contract_consumers.py, and the channels/threshold purity guards per the gaps below"
context:
  - tests/performance/test_single_writer.py
  - tests/performance/test_reachability.py
  - tests/test_contract_consumers.py
  - tests/load/channels/test_purity.py
  - tests/load/threshold/test_boundary.py
  - src/fitdocs/performance/engine.py
blocked_by: []
---

## What

`test_single_writer.py` scans import statements only:
`importlib.import_module("fitdocs.performance")` and an unaliased
`import fitdocs.performance.types` plus the `fitdocs.performance.derive_benchmarks`
attribute chain both pass the guard today. `test_reachability.py` relies on
the sibling guards for dynamic/attribute routes rather than checking them
itself. The channels/threshold import allowlists in `test_purity.py` and
`test_boundary.py` are one-directional (real imports ⊆ allowlist), so an
unused allowlist entry is silent. `FORBIDDEN_LITERALS` in the consumer
registry (`test_contract_consumers.py`) does not include the effort key
constants — `_E = "effort_distance_m"` in `engine.py` passes the guard
today.

## Why it matters

Each of these guards exists specifically to prevent an unsanctioned route
into a forbidden surface; the gaps mean that route is currently open and
undetected by the very test written to catch it.

## Evidence

- (4.5 r2 reviewer) "test_single_writer.py: add a name-level complement
  (flag `.attr`/`.id == 'derive_benchmarks'` in a non-sanctioned module)
  plus a string-literal scan for 'fitdocs.performance' in
  import_module/__import__ calls; importlib.import_module('fitdocs.performance')
  and unaliased `import fitdocs.performance.types` + attribute chain both
  pass today (design scopes the guard to import statements)."
- (5.1 r3 reviewer) "test_reachability.py's stated scope is import
  statements only; importlib.import_module / __import__ / `import fitdocs`
  + attribute routes from channels/threshold into fitdocs.performance are
  caught only by the sibling guards -- if either sibling weakens, 10.2
  loses that coverage silently."
- (5.1 reviewer) "tests/load/channels/test_purity.py and
  tests/load/threshold/test_boundary.py import allowlists are
  one-directional (real ⊆ allowlist); an unused allowlist entry is
  silent."
- (4.5 r2 reviewer) "test_contract_consumers.py: extend FORBIDDEN_LITERALS
  with the effort key constants so 10.3's 'no second spelling of an effort
  key' is pinned at the literal level (`_E = 'effort_distance_m'` in
  engine.py passes today)."

## How to pick it up

1. Read the four guard test modules listed in `area` and the current
   `engine.py` effort key constants.
2. Add a name-level complement and string-literal scan to
   `test_single_writer.py`; add the same dynamic/attribute coverage
   directly to `test_reachability.py` rather than relying on siblings.
3. Add the reverse-direction check (unused allowlist entries fail) to
   `test_purity.py`/`test_boundary.py`; extend `FORBIDDEN_LITERALS` with
   the effort key constants in `test_contract_consumers.py`.
</content>

## Additional gap (2026-09-12, feature-level validation)

- design § Allowed Dependencies claims a structural assertion that
  `fitdocs.performance` imports nothing from `fitdocs.render`, `fitdocs.sync`
  or `fitdocs.cli`; `tests/performance/test_purity.py` covers exactly the four
  pure modules, so `src/fitdocs/performance/engine.py`'s import surface is
  unguarded. Add an engine-level import allowlist (no `render`, `sync`, `cli`,
  `load.prompts`).
