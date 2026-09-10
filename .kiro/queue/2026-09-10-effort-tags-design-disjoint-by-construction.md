---
id: 2026-09-10-effort-tags-design-disjoint-by-construction
title: effort-tags design.md claims the three key classes are "disjoint by construction"; they are disjoint by test
status: open
importance: medium
importance_why: The code was corrected this run to say "held disjoint by test"; design.md still asserts the false version, so the spec and the module it specifies now disagree about what enforces the partition.
effort: S
kind: inconsistency
area: effort-tags, .kiro/specs/effort-tags/design.md, src/fitdocs/contract.py
created: 2026-09-10
surfaced_by: /kiro-impl effort-tags task 1.1 (round-3 adversarial review FOLLOW_UPS)
pinned_at: 91b2a98
resume_command: "do: correct .kiro/specs/effort-tags/design.md's Domain Model bullet so the MANAGED/USER disjointness is attributed to the test that enforces it, not to construction"
context:
  - .kiro/specs/effort-tags/design.md
  - src/fitdocs/contract.py
  - .kiro/specs/effort-tags/tasks.md
blocked_by: []
---

## What

`.kiro/specs/effort-tags/design.md` §Domain Model ends its frontmatter-key
ownership bullet with:

> The three are pairwise disjoint by construction.

For the `MANAGED_KEYS` / `USER_KEYS` pair this is false. Nothing in the
*construction* of either set prevents an overlap: both are hand-written
frozenset literals in `src/fitdocs/contract.py`, and adding `"effort"` to the
`MANAGED_KEYS` literal produces a module that imports and runs perfectly well
with the two sets overlapping. Only tests object.

The third class (everything else) is disjoint from both by definition, since it
is defined as the complement — so only the MANAGED/USER clause is wrong.

## Why it matters

`contract.py` was corrected during task 1.1 to say "disjoint, and held disjoint
by test", after a reviewer disproved the "by construction" phrasing by
mutation. The spec that the module implements still carries the original false
claim, so the two now disagree in a way that matters: a later reader who trusts
design.md will believe the partition is structurally guaranteed and may skip or
delete the disjointness test that is in fact the only thing enforcing it.

This is the same defect class that cost effort-tags 1.1 three review rounds —
prose asserting a mechanism that does not exist — and it is now sitting in the
upstream document rather than the code.

## Evidence

At `91b2a98`, `.kiro/specs/effort-tags/design.md:898-903`:

```
- **Frontmatter key ownership** now partitions the block three ways:
  `MANAGED_KEYS` (fitdocs writes and restores), `USER_KEYS` (the athlete
  writes; fitdocs carries verbatim, never writes), and everything else
  (unmanaged; dropped with a warning). The three are pairwise disjoint by
  construction.
```

Disproved by the round-3 reviewer on branch `impl/effort-tags`: adding
`"effort"` to the `MANAGED_KEYS` literal yields a module that imports and runs
with the sets overlapping; the failures are all test failures
(`test_user_keys_is_disjoint_with_managed_keys`, the emittable anti-drift
equality, and `tests/test_ownership_contract.py::test_managed_keys_equal_contract_exactly`).

The corrected wording now shipped in `src/fitdocs/contract.py` (task 1.1,
commit `93c4805` on `impl/effort-tags`) reads:

> ``MANAGED_KEYS`` and ``USER_KEYS`` are disjoint, and held disjoint by test.

## How to pick it up

1. Open `.kiro/specs/effort-tags/design.md` and find the Domain Model bullet on
   frontmatter key ownership (near line 898).
2. Compare against the module docstring in `src/fitdocs/contract.py`, which
   already carries the corrected phrasing — reuse its wording rather than
   inventing a third formulation. (Three separate formulations of a neighbouring
   sentence were rejected during task 1.1; do not add a fourth.)
3. Done means: design.md attributes the MANAGED/USER disjointness to the test
   that enforces it, and no other claim in that bullet asserts a guarantee the
   code does not provide.

## Open questions

Whether the design intends the disjointness to *become* structural — e.g. by
deriving `MANAGED_KEYS` and `USER_KEYS` from a single partitioned source rather
than two independent literals. If so, this becomes an implementation item
rather than a wording fix, and the spec sentence is aspirational rather than
false. Task 1.1's boundary explicitly forbade touching `MANAGED_KEYS`, so that
decision was out of scope for the run that surfaced this.
