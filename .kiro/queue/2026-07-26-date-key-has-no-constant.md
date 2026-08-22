---
id: 2026-07-26-date-key-has-no-constant
title: '`"date"` is the only managed frontmatter key with no `Final[str]` constant, and it is hardcoded at three sites'
status: open
importance: low
importance_why: Not a correctness risk today — the reader's key is mutation-pinned — but it is exactly the drift wiki-contract's own revalidation item is watching for, and every sibling key already has a constant.
effort: S
kind: inconsistency
area: wiki-contract, src/fitdocs/contract.py, src/fitdocs/render/frontmatter.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 5.1 completion verification)
pinned_at: c5ce672
resume_command: "do: add a DATE_KEY Final[str] constant to contract.py alongside its siblings and route MANAGED_KEYS, document_date and the renderer's write through it [queue: .kiro/queue/2026-07-26-date-key-has-no-constant.md]"
context:
  - src/fitdocs/contract.py
  - src/fitdocs/render/frontmatter.py
  - .kiro/specs/wiki-contract/design.md
blocked_by: []
---

## What
`src/fitdocs/contract.py:174-186` defines a `Final[str]` constant for every
managed frontmatter key — `TYPE_KEY`, `GENERATOR_KEY`, `DOC_VERSION_KEY`,
`UUID_KEY`, `SOURCES_KEY` — except `"date"`, which is instead written as a bare
literal at three independent sites:

- `src/fitdocs/contract.py:219` — `MANAGED_KEYS` membership
- `src/fitdocs/contract.py:484` — `document_date`'s `frontmatter.get("date")`
- `src/fitdocs/render/frontmatter.py:109` — the renderer's write

## Why it matters
Low, deliberately: this is not a live correctness risk. A task 5.1 verification
pass mutated the reader's key (`get("date")` → `get("activity_date")`) and it
reddened two `tests/test_contract.py` cases plus two in `tests/load/`, so the
reader's spelling is pinned by tests.

It matters because it is the *named* drift target of an existing obligation.
`.kiro/specs/wiki-contract/design.md:87-93` item 5 commits to revalidating
`document_date` and athlete-benchmarks' engine date resolution on "any later
change to this module's reader set, to `MANAGED_KEYS`, or **to the on-disk form
of the frontmatter `date` key**". Three uncoordinated literals is the cheapest
way for that on-disk form to change at one site and not the others — and the
consistency argument is already settled for every sibling key.

## Evidence
At `c5ce672`:

```
grep -n '_KEY: Final' src/fitdocs/contract.py     # TYPE, GENERATOR, DOC_VERSION, UUID, SOURCES -- no DATE
grep -rn '"date"' src/fitdocs/contract.py src/fitdocs/render/frontmatter.py
  contract.py:219   (MANAGED_KEYS)
  contract.py:484   (document_date)
  render/frontmatter.py:109  (the write)
```

## How to pick it up
1. Read `src/fitdocs/contract.py:174-186` for the sibling constants' naming and typing convention, and `:219` for how `MANAGED_KEYS` is assembled.
2. Add `DATE_KEY: Final[str] = "date"` and route all three sites through it. Decide whether `DATE_KEY` joins the module's `__all__` — check what the siblings do; `tests/test_public_api.py` pins the contract's published surface, so adding it there is a surface change that needs the pin updated.
3. Done looks like: `"date"` appears as a literal exactly once in `src/`, and the existing `document_date` and frontmatter tests still pass unchanged.

**This is `wiki-contract`'s to land, not athlete-benchmarks'.** Task 5.1
explicitly forbids touching "no key constant and no managed-key membership", so
it was correctly left alone there. Note `wiki-contract` may need an open task
before its module can be edited — the same vehicle problem recorded in
[[2026-07-26-plugin-surface-list-stale-after-amendment-3]].

Related: [[2026-07-26-frontmatter-date-vs-filename-date-unasserted]] — the other
half of how the reader and writer could drift apart.
