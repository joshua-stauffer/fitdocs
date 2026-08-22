---
id: 2026-07-25-wiki-contract-load-keys-landed
title: The wiki-contract LOAD_KEYS roadmap item is done but still shows open
status: done
importance: medium
importance_why: Misdirects planning — any planner reading roadmap.md sees a wiki-contract prerequisite that no longer exists.
effort: S
kind: inconsistency
area: wiki-contract, .kiro/steering/roadmap.md
created: 2026-07-25
surfaced_by: /kiro-queue verification pass
pinned_at: 2a01dfd
resume_command: "do: confirm LOAD_KEYS/MANAGED_KEYS need no further wiki-contract change, then tick roadmap.md:432 and note where the work landed"
context:
  - .kiro/steering/roadmap.md
  - src/fitdocs/contract.py
  - .kiro/specs/training-load/tasks.md
blocked_by: []
---

## What

`.kiro/steering/roadmap.md:432` lists an open `- [ ] wiki-contract` follow-up:
`contract.py` hardcodes `LOAD_KEYS = ("load_points", "load_methodology",
"load_zone")`, `load_zone` is vocabulary from the withdrawn methodology, and the tuple must move with
the redefined load result or `check` reports unmanaged keys.

That work has landed. It was absorbed into `training-load` task 2.4 as a
declared cross-boundary incursion into wiki-contract's module, so no separate
wiki-contract pass ever ran and nobody ticked the roadmap line.

## Why it matters

The roadmap is what `/kiro-spec-batch`, `/kiro-queue`, and any planning session
read to decide what must land before Phase 4. As written it advertises a
wiki-contract prerequisite that does not exist, and it describes `LOAD_KEYS`
with values the code no longer holds — so a session that trusts it will either
schedule dead work or reason from a stale contract.

## Evidence

Verified at `2a01dfd`:

- `src/fitdocs/contract.py:187` — `LOAD_KEYS` is now
  `("load_value", "load_methodology", "load_basis")`. The roadmap's quoted
  tuple is stale in all three positions.
- `grep -rn "load_points\|load_zone" src/ tests/` — no hits outside three
  docstrings in `contract.py` and `load/docedit.py` describing the *old* key
  the new one replaces. The withdrawn methodology's vocabulary is gone from live code.
- `.kiro/specs/training-load/tasks.md:168` — task 2.4, "Rename the managed load
  frontmatter keys atomically with the document-format version", is `[x]`.
- Commit `a782034` — `feat(training-load): rename the managed load frontmatter
  keys with the doc-format version (task 2.4)`.
- `.kiro/specs/training-load/tasks.md:229` names task 2.4 as the precedent for
  declared cross-boundary incursions into the document-contract module, which
  is why this landed under training-load rather than wiki-contract.

## How to pick it up

1. Read `src/fitdocs/contract.py:185-245` and confirm `LOAD_KEYS`,
   `MANAGED_KEYS` and the anti-drift test that pins them together are
   consistent with the redefined `LoadResult` — this item asserts the *rename*
   landed, not that wiki-contract has no remaining work at all.
2. Run the suite's contract tests to confirm `check` reports no unmanaged keys.
3. Tick `roadmap.md:432` and replace the stale tuple with a one-line note that
   the work landed in `training-load` task 2.4 (commit `a782034`), so the
   history stays legible.

Done means: the roadmap line is checked, its quoted tuple matches the code, and
the pointer to where the work actually landed is recorded.

## Open questions

Whether the roadmap should keep completed `Existing Spec Updates` lines as
`- [x]` with a landing note (the convention the `Direct Implementation
Candidates` section already uses) or move them out. The `settings-foundation`
entry at `roadmap.md:154` suggests the former.

## Resolution

**Done 2026-07-26** (queue sweep, merged to `main` at `e806c57`).

`c4243e6`. Both stale roadmap lines ticked with landing notes written from the shipped tree. Scope grew: the `training-load` line at roadmap.md:410 was also stale and is ticked too. Two review rounds rejected notes asserting a `LoadCalculator.supports(activity)` member that `3121bb6` deliberately removed; the wider spread across Phase 4 specs is tracked at `2026-07-26-phase4-specs-pin-withdrawn-supports-member`.
