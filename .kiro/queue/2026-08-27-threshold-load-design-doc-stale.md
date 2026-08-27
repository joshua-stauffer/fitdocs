---
id: 2026-08-27-threshold-load-design-doc-stale
title: threshold-load design.md carries ten now-false claims, including two fired revalidation triggers it never records
status: open
importance: high
importance_why: design.md is the source of truth a later session reads; it now misdescribes supports()'s semantics and which modules touch ProfileView.
effort: S
kind: doc-drift
area: threshold-load, .kiro/specs/threshold-load/design.md
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
pinned_at: 3e14ab9
resume_command: "/kiro-impl threshold-load [queue: .kiro/queue/2026-08-27-threshold-load-design-doc-stale.md] Amend design.md to match what shipped"
context:
  - .kiro/specs/threshold-load/design.md
  - src/fitdocs/load/threshold/calculator.py
  - src/fitdocs/load/arbitrate.py
blocked_by: []
---

## What

`.kiro/specs/threshold-load/design.md` was **not modified at all** on
`impl/threshold-load`, while the adjacent `.kiro/specs/plugin-api/design.md`
was updated for truth maintenance. Ten claims in it are now false:

1. `:61`, `:1069-1070` — "the registry's modality prefilter runs first". False
   on the forced/default path: `arbitrate.py:129-131` returns
   `Selected(registry.get(forced_id))` with no `for_modality` and no
   `supports_activity`. **This is a fired revalidation trigger.**
2. `:715-717` — "`SUPPORTED_SPORTS` is what the calculator's `supports` answer
   reads". It reads `SUPPORTED_SPORTS` **and** `DECLARED_MODALITIES`
   (`calculator.py:326-328`).
3. `:718-720` — "a strength activity never reaches `compute`". True only
   *because* of the modality conjunct design denies exists.
4. `:1023-1027`, `:1058-1059` — the `supports` description and its docstring.
5. `:805` — "the only module that calls `ProfileView.benchmark`/
   `has_benchmark`". `load/prompts.py:111` also calls `has_benchmark`.
   Corrected in `anchors.py`'s own docstring; **not** in design.md. **Second
   fired trigger.**
6. `:1174` — "the selected channel's own `inputs_used` ... already carries the
   anchor value, its discipline and its measurement date". True for power only.
   See `2026-08-27-anchor-provenance-missing-for-pace-and-hr`.
7. `:392-396` — `threshold/__init__.py` "re-exports the calculator and its
   constants". It deliberately re-exports nothing and documents why.
8. `:421-426` — `engine.py` "not modified by this feature". It is (docstring
   only, AST-identical), as are `registry.py` and `plugins.py`.
9. `:297-299`, `:1022` — "a frozen dataclass instance satisfies it with no
   privilege a plugin author lacks". It needs `cast(LoadCalculator, ...)` under
   `mypy --strict`.
10. `:327`, `:578-580`, `:430-436` — graph edges that do not exist
    (`Bench --> Disc`; calculator.py inbound to priority.py) and a test-file
    enumeration four modules short.

## Why it matters

A session reading design.md as the source of truth would be actively misled
about `supports()`'s semantics — the one thing on this spec that required a
deliberate departure from the written design — and about which modules touch
`ProfileView`.

## Evidence

`3e14ab9`. `git diff --stat main...HEAD -- .kiro/specs/threshold-load/` shows only
`tasks.md`. Each claim verified against the shipped source by the feature-level
design validator; line references above.

## How to pick it up

Write an Amendment section at the top of design.md, in the style of Amendments
1 and 2 already there, recording: the modality conjunct and why (the
prefilter premise is false on the forced/default path); the `prompts.py`
sole-caller correction; the `cast`; and the `inputs_used` anchor claim. Then
fix the file-structure and graph-edge details inline.
