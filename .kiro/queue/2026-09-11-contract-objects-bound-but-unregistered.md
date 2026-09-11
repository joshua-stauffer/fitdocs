---
id: 2026-09-11-contract-objects-bound-but-unregistered
title: Twelve contract objects are bound by converted modules but absent from CONTRACT_BINDINGS
status: open
importance: medium
importance_why: The identity guard does not cover them, so any of the twelve could be shadowed by a local copy with the suite green.
effort: M
kind: gap
area: tests/test_contract_consumers.py, src/fitdocs/contract.py
created: 2026-09-11
surfaced_by: /kiro-impl effort-tags 5.1 review, recounted by 5.3 feature validation
pinned_at: d1147a0
resume_command: "do: register or mechanically derive the contract bindings that CONTRACT_BINDINGS omits"
context:
  - tests/test_contract_consumers.py
  - src/fitdocs/contract.py
blocked_by: []
---

## What

`CONTRACT_BINDINGS` has always been a curated list rather than a derived one.
Applying the predicate "name is in `contract.__all__`, `getattr(mod, name) is
getattr(contract, name)`, and not in that module's `CONTRACT_BINDINGS` tuple"
finds twelve bindings the identity check does not cover:

| Module | Unregistered |
|---|---|
| `fitdocs.sync` | `DOC_VERSION`, `InvalidEffortTag`, `document_version` |
| `fitdocs.load.engine` | `DOC_VERSION`, `document_date`, `document_version` |
| `fitdocs.load.docedit` | `begin_marker`, `end_marker` |
| `fitdocs.render.frontmatter` | `GENERATOR`, `GENERATOR_KEY` |
| `fitdocs.render.views` | `DOC_BANNER` |
| `fitdocs.audit` | `InvalidEffortTag` |

Two are new with effort-tags (`InvalidEffortTag` in both `sync` and `audit`,
already on `main`); the other ten pre-date it.

Note the count is predicate-dependent: an earlier pass counted eleven. Whoever
picks this up should re-derive the list with an explicit, recorded rule rather
than trusting either number.

## Why it matters

The registry exists so that a module cannot quietly define a second reader or a
second spelling of a contract value. Every omitted name is a hole in exactly
that guarantee -- `sync` and `audit` could each grow a local `InvalidEffortTag`
and no test would object. The gap grows every time a spec adds a contract import
without touching the registry, and nothing prompts that.

## Evidence

Enumerated over `CONVERTED_MODULES` versus `CONTRACT_BINDINGS` during task 5.3
validation at `e39b35f`; the table above is that run's output.

Task 5.1's review independently established the guard is the sole detector: with
five registered entries removed and five same-named shadow copies installed, the
whole suite stays green.

## How to pick it up

1. Re-derive the list with the predicate written down, and record it in the task
   -- do not start from the table above.
2. Decide curated-versus-derived. Deriving each module's expected tuple from its
   `from fitdocs.contract import (...)` AST closes this item and
   `2026-09-11-contract-bindings-value-emptying-undetected` together, and makes
   the registry self-maintaining.
3. If you instead register the twelve by hand, add whatever makes the next
   omission fail loudly -- otherwise this item recurs.

Done looks like: a module importing a contract name it has not registered fails
a test, whichever mechanism gets it there.
