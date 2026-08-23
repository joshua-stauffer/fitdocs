---
id: 2026-07-30-exemption-list-cannot-detect-a-duplicate-entry
title: The ConstantGuard exemption list's unused-entry check cannot detect an exact duplicate entry
status: open
importance: low
importance_why: Set membership makes two identical exemption entries both "used", so the list can accumulate redundant entries without reddening — the same class of quiet widening the unused-entry assertion was written to prevent.
effort: S
kind: gap
area: fit-ingest, tests/metrics/test_constant_guard.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.2, reviewer follow-up round 1)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-exemption-list-cannot-detect-a-duplicate-entry.md] Make the exemption list reject duplicate entries, not only unused ones"
context:
  - tests/metrics/test_constant_guard.py
  - .kiro/steering/change-protocol.md
  - .kiro/specs/fit-ingest/design.md
blocked_by: []
---

## What

`test_no_exemption_entry_is_unused` in `tests/metrics/test_constant_guard.py`
checks that every `_EXEMPTIONS` entry matches a real literal site. It does this
by set membership, so two byte-identical entries both match the same site and
both count as used. The list can therefore hold duplicates indefinitely without
any test reddening.

## Why it matters

Low, and genuinely low: a duplicate exemption grants no coverage that the
original did not already grant, so this cannot let an uncited literal through.

It matters as hygiene on the assertion that exists specifically to stop the
exemption list widening quietly. Task 12.2's review found two separate ways
the guard could be defeated, both of them "the bookkeeping looks complete but
the key is too weak" — a set of `(line, value)` that absorbed an injected
literal, and a `>= 6` file-count control that passed on the wrong directory.
Both were fixed. This is the same shape one level down, left open because the
consequence is redundancy rather than a hole.

## Evidence

At `2d69443` plus the uncommitted task 12.2 work, in
`tests/metrics/test_constant_guard.py`: the unused-entry test builds a set of
scanned literal keys and asserts each exemption's key is in it. Set membership
is not multiplicity, so `entry in scanned` is true for the second copy of any
entry exactly as it is for the first.

Reported by the task 12.2 reviewer as a follow-up alongside a related
suggestion — that `documented_out_of_scope_cited_constants` in
`tests/metrics/test_sources.py` has no cardinality assertion either. The
reviewer verified by mutation that *that* set cannot silently absorb a second
member (two independent layers red), so only the duplicate-entry case below
is open. Not independently re-verified by the parent session; the mechanism is
visible by reading.

## How to pick it up

1. Open `test_no_exemption_entry_is_unused` in
   `tests/metrics/test_constant_guard.py`.
2. Add a uniqueness assertion over `_EXEMPTIONS` — comparing `len(_EXEMPTIONS)`
   against the length of the set of its keys is enough, and states the intent
   directly.
3. Verify by mutation per `.kiro/steering/change-protocol.md` § Fixture
   Discrimination: duplicating any one entry must red the new assertion and
   nothing else. Run it through `uv run pytest`.

While there, consider whether the same check belongs on the exemption list's
*coverage* direction (a literal site matched by two different entries), which
has the same set-membership shape.

Done looks like: duplicating an exemption entry reds a named assertion.
