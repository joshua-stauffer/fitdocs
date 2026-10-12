---
id: 2026-10-12-chart-kit-guard-hardening
title: Harden the kit's boundary and theme guards (stdlib allow-list, dynamic attrs, inline styles, enum types)
status: open
importance: medium
importance_why: Guards that pass known evasions give false confidence.
effort: S
kind: test-gap
area: chart-kit tests (test_boundary, test_theme_coverage, test_data/test_schema)
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-guard-hardening.md] Harden the kit's boundary and theme guards (stdlib allow-list, dynamic attrs, inline styles, enum types)"
context:
  - tests/render/charts/kit/test_boundary.py
  - tests/render/charts/kit/test_theme_coverage.py
  - tests/render/charts/kit/test_data.py
  - tests/render/charts/kit/test_schema.py
  - tests/compose/test_boundary.py
blocked_by: []
---

## What
(1) test_boundary bans named stdlib roots, so unlisted ones (sqlite3, asyncio) pass; an allow-list of the stdlib roots the kit uses would close the class (compose and connectors guards share the shape). (2) `getattr(datetime, 'n'+'ow')()` evades every AST clock guard in the repo. (3) The theme walk does not check colours inside inline `style` attributes or `color`/`stop-color`/`flood-color`. (4) StrEnum-ness of ValueKind/ProblemCode/Output/OptionType/OverBound is unpinned (tests compare name/value only; `Enum as StrEnum` likely survives).

## Why it matters
Each is a mutation that survives today.

## Evidence
6.5 review mutations F3/F4 (sqlite3, asyncio green), M5; 6.3 review F2 (inline style rgb green); 2.4 review O23 species.

## How to pick it up
Add the stdlib allow-list with a positive control per root; extend `_colours_allowed` to inline style values; add `issubclass(X, StrEnum)` pins; run each listed mutation red.
